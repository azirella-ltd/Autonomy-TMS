"""
SAP Config Builder Service

Builds a SupplyChainConfig from extracted SAP S/4HANA and APO data.
This is the reverse path: SAP extraction → working SupplyChainConfig.

Three modes:
- Preview: Analyze extracted data, show what will be created
- Build: Create all entities in DB at once, return config_id
- Step-by-Step: Execute one pipeline step at a time with anomaly detection

8-Step Build Pipeline:
1. Extract & Validate
2. Company & Geography
3. Sites with Master Type Inference
4. Products & Hierarchy
5. Transportation Lanes (Priority Cascade)
6. Trading Partners & Sourcing
7. Manufacturing & BOM
8. Planning Data (Inventory, Forecasts)
"""

import json
import logging
import pathlib
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime, date, timedelta
from dataclasses import dataclass, field
from collections import Counter

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text as sql_text

import app.models  # noqa: F401 - ensures all models are loaded

from app.models.supply_chain_config import SupplyChainConfig, Site, TransportationLane, Market
from app.models.sc_entities import (
    Product, Forecast, InvLevel, InvPolicy,
    TradingPartner, Geography,
    SourcingRules, ProductBom, ProductionProcess,
    OutboundOrder, OutboundOrderLine, InboundOrder, InboundOrderLine,
    Shipment,
)
from app.models.production_order import ProductionOrder, ProductionOrderComponent
from app.models.quality_order import QualityOrder
from app.models.supplier import VendorProduct, VendorLeadTime
from app.models.tenant import Tenant

from app.models.planning_hierarchy import SiteHierarchyNode, ProductHierarchyNode
from app.integrations.sap.data_mapper import SupplyChainMapper
from app.services.sap_field_mapping_service import (
    SAPFieldMappingService,
    create_field_mapping_service,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# UN M49 region reference — loaded once from bundled JSON
# ---------------------------------------------------------------------------
_UN_M49_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "un_m49_regions.json"


def _load_country_to_continent() -> Dict[str, str]:
    """Build ISO alpha-2 → continent name lookup from UN M49 JSON."""
    with open(_UN_M49_PATH, "r") as f:
        data = json.load(f)
    lookup: Dict[str, str] = {}
    for continent_name, info in data["continents"].items():
        for code in info["countries"]:
            lookup[code] = continent_name
    return lookup


# Singleton lookup — {ISO alpha-2 → continent name}
_COUNTRY_TO_CONTINENT: Dict[str, str] = _load_country_to_continent()


# Master type constants — use AWS SC canonical names for boundary nodes
MASTER_MANUFACTURER = "MANUFACTURER"
MASTER_INVENTORY = "INVENTORY"
MASTER_VENDOR = "VENDOR"
MASTER_CUSTOMER = "CUSTOMER"
# Legacy aliases pointing to canonical names
MASTER_VENDOR = "VENDOR"
MASTER_CUSTOMER = "CUSTOMER"


@dataclass
class SitePreview:
    """Preview of a site to be created."""
    key: str
    name: str
    inferred_master_type: str
    product_count: int = 0
    has_bom: bool = False
    is_vendor_location: bool = False
    is_customer_destination: bool = False
    address_number: str = ""  # SAP ADRNR — links to ADRC geography


@dataclass
class LanePreview:
    """Preview of a transportation lane to be created."""
    from_key: str
    to_key: str
    source: str  # apo_trlane, eord, ekpo_history, delivery_history
    product_count: int = 0
    lead_time_days: int = 0


@dataclass
class ConfigPreview:
    """Preview of what the build will create."""
    sites: List[SitePreview] = field(default_factory=list)
    lanes: List[LanePreview] = field(default_factory=list)
    products_total: int = 0
    products_with_bom: int = 0
    products_with_forecast: int = 0
    vendors: int = 0
    customers: int = 0
    sourcing_rules: int = 0
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sites": [
                {
                    "key": s.key, "name": s.name,
                    "inferred_master_type": s.inferred_master_type,
                    "product_count": s.product_count,
                }
                for s in self.sites
            ],
            "lanes": [
                {
                    "from": l.from_key, "to": l.to_key,
                    "source": l.source, "product_count": l.product_count,
                }
                for l in self.lanes
            ],
            "products": {
                "total": self.products_total,
                "with_bom": self.products_with_bom,
                "with_forecast": self.products_with_forecast,
            },
            "vendors": self.vendors,
            "customers": self.customers,
            "sourcing_rules": self.sourcing_rules,
            "warnings": self.warnings,
        }


# Step-by-step build support
STEP_NAMES = {
    1: "Data Validation",
    2: "Geography",
    3: "Sites",
    4: "Products",
    5: "Partners & Sourcing",
    6: "BOM & Manufacturing",
    7: "Planning Data",
    8: "Transactional Data",
    9: "Transportation Lanes",
}

STEP_ENTITY_TYPES = {
    1: "validation",
    2: "geography",
    3: "site",
    4: "product",
    5: "trading_partner",
    6: "product_bom",
    7: "forecast",
    8: "orders",
    9: "transportation_lane",
}

# Known standard SAP table names (for Z-table detection)
KNOWN_SAP_TABLES = {
    "MARA", "MARC", "MARD", "MARM", "MVKE",
    "T001W", "T001", "ADRC",
    "LFA1", "KNA1", "KNVV",
    "STPO", "STKO",
    "EKKO", "EKPO", "EKET",
    "VBAK", "VBAP",
    "LIKP", "LIPS",
    "AFKO", "AFPO",
    "RESB",
    "EINA", "EINE", "EORD",
    "PLKO", "PLPO",
    "CRHD", "KAKO",
    "/SAPAPO/LOC", "/SAPAPO/SNPFC", "/SAPAPO/MATLOC",
    "/SAPAPO/TRLANE", "/SAPAPO/PDS", "/SAPAPO/SNPBV",
}


@dataclass
class StepResult:
    """Result from executing one build step."""
    step: int
    step_name: str
    entities_created: int = 0
    entity_type: str = ""
    sample_data: List[Dict[str, Any]] = field(default_factory=list)
    anomalies: List[Dict[str, Any]] = field(default_factory=list)
    z_tables: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    # For step 1 (validation): table inventory
    table_inventory: List[Dict[str, Any]] = field(default_factory=list)
    # Config tracking
    config_id: Optional[int] = None
    completed_steps: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "step_name": self.step_name,
            "entities_created": self.entities_created,
            "entity_type": self.entity_type,
            "sample_data": self.sample_data,
            "anomalies": self.anomalies,
            "z_tables": self.z_tables,
            "warnings": self.warnings,
            "table_inventory": self.table_inventory,
            "config_id": self.config_id,
            "completed_steps": self.completed_steps,
            "total_steps": 9,
        }


class SAPConfigBuilder:
    """
    Orchestrator that takes extracted SAP data and builds a complete
    SupplyChainConfig with all entities.
    """

    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self.mapper = SupplyChainMapper()
        self._field_mapping_service = create_field_mapping_service(db, tenant_id)

        # Extracted data (DataFrames)
        self._data: Dict[str, pd.DataFrame] = {}

        # Created entities (for cross-referencing)
        self._config: Optional[SupplyChainConfig] = None
        self._sites: Dict[str, Site] = {}
        self._products: Dict[str, Product] = {}
        self._trading_partners: Dict[str, Any] = {}
        self._partner_ids: Dict[str, int] = {}  # business_key → TradingPartner._id (populated after upsert)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def suggest_config_name(sap_data: Dict[str, pd.DataFrame]) -> str:
        """
        Derive a meaningful SC config name from SAP data.

        Priority cascade:
        1. T001 company name (BUTXT) — e.g. "ACME Corp SC Network"
        2. T001W plant names — e.g. "Hamburg + Berlin SC Network"
        3. Fallback — "SAP Import"
        """
        # Try T001 company name first
        t001 = sap_data.get("T001", pd.DataFrame())
        if not t001.empty:
            butxt_col = None
            for col in ["BUTXT", "butxt", "Butxt"]:
                if col in t001.columns:
                    butxt_col = col
                    break
            if butxt_col:
                names = t001[butxt_col].dropna().unique()
                names = [str(n).strip() for n in names if str(n).strip()]
                if len(names) == 1:
                    return f"{names[0]} SC Network"
                elif len(names) > 1:
                    return f"{names[0]} (+{len(names) - 1}) SC Network"

        # Try T001W plant names
        t001w = sap_data.get("T001W", pd.DataFrame())
        if not t001w.empty:
            name_col = None
            for col in ["NAME1", "name1", "Name1"]:
                if col in t001w.columns:
                    name_col = col
                    break
            werks_col = None
            for col in ["WERKS", "werks", "Werks"]:
                if col in t001w.columns:
                    werks_col = col
                    break

            if name_col:
                plant_names = t001w[name_col].dropna().unique()
                plant_names = [str(n).strip() for n in plant_names if str(n).strip()]
                if len(plant_names) == 1:
                    return f"{plant_names[0]} SC Network"
                elif len(plant_names) == 2:
                    return f"{plant_names[0]} & {plant_names[1]} SC Network"
                elif len(plant_names) > 2:
                    return f"{plant_names[0]} (+{len(plant_names) - 1} sites) SC Network"
            elif werks_col:
                codes = t001w[werks_col].dropna().unique()
                codes = [str(c).strip() for c in codes if str(c).strip()]
                if codes:
                    return f"Plants {', '.join(codes[:3])} SC Network"

        return "SAP Import"

    async def preview(
        self,
        sap_data: Dict[str, pd.DataFrame],
        config_name: str = "SAP Import",
        plant_filter: Optional[List[str]] = None,
        company_filter: Optional[str] = None,
    ) -> ConfigPreview:
        """
        Dry-run analysis — extract data, infer topology, return preview.

        Args:
            sap_data: Dict of table_name → DataFrame (from connectors or CSV)
            config_name: Name for the config
            plant_filter: Optional list of plant codes to include
            company_filter: Optional company code to filter by

        Returns:
            ConfigPreview with inferred sites, lanes, products, warnings
        """
        self._data = sap_data
        self._apply_filters(plant_filter, company_filter)

        preview = ConfigPreview()

        # Step 1: Validate required tables
        self._validate_required_tables(preview)

        # Step 3: Infer sites with master types
        site_previews = self._infer_sites(preview)
        preview.sites = site_previews

        # Step 4: Count products
        mara = self._data.get("MARA", pd.DataFrame())
        marc = self._data.get("MARC", pd.DataFrame())
        stpo = self._data.get("STPO", pd.DataFrame())
        if not mara.empty:
            preview.products_total = len(mara["MATNR"].unique()) if "MATNR" in mara.columns else 0
        elif not marc.empty:
            preview.products_total = len(marc["MATNR"].unique()) if "MATNR" in marc.columns else 0

        if not stpo.empty and "MATNR" in stpo.columns:
            preview.products_with_bom = len(stpo["MATNR"].unique())

        # Step 5: Infer lanes
        lane_previews = self._infer_lanes(preview)
        preview.lanes = lane_previews

        # Step 6: Count partners
        lfa1 = self._data.get("LFA1", pd.DataFrame())
        kna1 = self._data.get("KNA1", pd.DataFrame())
        eord = self._data.get("EORD", pd.DataFrame())
        if not lfa1.empty and "LIFNR" in lfa1.columns:
            preview.vendors = len(lfa1["LIFNR"].unique())
        if not kna1.empty and "KUNNR" in kna1.columns:
            preview.customers = len(kna1["KUNNR"].unique())
        if not eord.empty:
            preview.sourcing_rules = len(eord)

        # Step 8: Forecasts
        snpfc = self._data.get("/SAPAPO/SNPFC", pd.DataFrame())
        snpbv = self._data.get("/SAPAPO/SNPBV", pd.DataFrame())
        if not snpfc.empty and "MATNR" in snpfc.columns:
            preview.products_with_forecast = len(snpfc["MATNR"].unique())
        elif not snpbv.empty and "MATNR" in snpbv.columns:
            preview.products_with_forecast = len(snpbv["MATNR"].unique())

        return preview

    async def build(
        self,
        sap_data: Dict[str, pd.DataFrame],
        config_name: str = "SAP Import",
        plant_filter: Optional[List[str]] = None,
        company_filter: Optional[str] = None,
        master_type_overrides: Optional[Dict[str, str]] = None,
        options: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Any] = None,
        geocoding_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Build a SupplyChainConfig from SAP data.

        Args:
            sap_data: Dict of table_name → DataFrame
            config_name: Name for the config
            plant_filter: Optional plant filter
            company_filter: Optional company filter
            master_type_overrides: User corrections from preview step
            options: Build options (include_forecasts, include_inventory, etc.)

        Returns:
            Dict with config_id and summary counts
        """
        self._data = sap_data
        self._apply_filters(plant_filter, company_filter)

        opts = options or {}
        overrides = master_type_overrides or {}

        async def _report(step: int, total: int, desc: str):
            if progress_callback:
                await progress_callback(step, total, desc)

        try:
            total_steps = 10

            # Step 1: Create config (also deactivates previous active configs)
            await _report(1, total_steps, "Creating supply chain config...")
            self._config = await self._create_config(config_name)

            # Step 2: Geography (insert rows, start geocoding in background)
            await _report(2, total_steps, "Creating geography records & starting geocoding...")
            geocode_coro = await self._create_geography(geocoding_callback=geocoding_callback)

            # Launch geocoding as a concurrent task — it runs in parallel with
            # steps 3-8 which don't need coordinates. We await it before step 9
            # (transportation lanes) which uses coordinates for lead time calc.
            import asyncio
            geocode_task = None
            if geocode_coro is not None:
                geocode_task = asyncio.create_task(geocode_coro())

            # Step 3: Sites
            await _report(3, total_steps, "Creating sites from plants & storage locations...")
            site_count = await self._create_sites(overrides, opts)

            # Step 4: Products
            await _report(4, total_steps, "Creating products from material master...")
            product_count = await self._create_products()

            # Step 5: Site & Product Hierarchy Nodes
            await _report(5, total_steps, "Building site geo hierarchy & product hierarchy nodes...")
            hierarchy_counts = await self._create_hierarchy_nodes()

            # Step 6: Trading Partners & Sourcing
            await _report(6, total_steps, "Creating trading partners & sourcing rules...")
            vendor_count, customer_count, sourcing_count = await self._create_partners_and_sourcing()

            # Step 7: BOM & Manufacturing
            await _report(7, total_steps, "Building bill of materials...")
            bom_count = await self._create_bom_and_manufacturing()

            # Step 8: Planning Data
            await _report(8, total_steps, "Generating forecasts & inventory policies...")
            forecast_count = 0
            inv_count = 0
            if opts.get("include_forecasts", True):
                forecast_count = await self._create_forecasts(
                    horizon_weeks=opts.get("forecast_horizon_weeks", 52)
                )
            if opts.get("include_inventory", True):
                inv_count = await self._create_inventory(
                    default_policy=opts.get("default_inv_policy", "doc_dem"),
                    safety_days=opts.get("default_safety_days", 14),
                )

            # Step 9: Transactional Data (orders, production orders, quality orders)
            await _report(9, total_steps, "Importing orders & transactional data...")
            order_counts = await self._create_transactional_data(opts)

            # Await geocoding completion before step 10 (lanes need coordinates
            # for distance-based lead time calculation)
            if geocode_task is not None:
                await _report(10, total_steps, "Waiting for geocoding to complete...")
                await geocode_task

            # Step 10: Transportation Lanes (after transactions so we can
            # infer lanes from EKKO/EKPO/VBAK/VBAP/LIKP/LIPS if available,
            # falling back to EORD source list + full connectivity default)
            await _report(10, total_steps, "Inferring transportation lanes from sourcing & shipping data...")
            lane_count = await self._create_lanes()

            await self.db.commit()

            return {
                "config_id": self._config.id,
                "config_name": config_name,
                "summary": {
                    "sites": site_count,
                    "products": product_count,
                    "site_hierarchy_nodes": hierarchy_counts.get("site_nodes", 0),
                    "product_hierarchy_nodes": hierarchy_counts.get("product_nodes", 0),
                    "lanes": lane_count,
                    "vendors": vendor_count,
                    "customers": customer_count,
                    "bom_entries": bom_count,
                    "sourcing_rules": sourcing_count,
                    "forecasts": forecast_count,
                    "inventory_records": inv_count,
                    **order_counts,
                },
            }

        except Exception:
            # Roll back the entire transaction — this undoes ALL flushes
            # (new config, deactivation of old configs, all child entities).
            # The old active config is restored to is_active=true automatically.
            await self.db.rollback()
            raise

    # ------------------------------------------------------------------
    # Step-by-Step Public API
    # ------------------------------------------------------------------

    async def start_build(
        self,
        sap_data: Dict[str, pd.DataFrame],
        config_name: str = "SAP Import",
        plant_filter: Optional[List[str]] = None,
        company_filter: Optional[str] = None,
    ) -> StepResult:
        """
        Step 1: Create config, validate tables, detect Z-tables.

        Returns StepResult with table inventory, validation warnings,
        and detected Z-tables.
        """
        self._data = sap_data
        self._apply_filters(plant_filter, company_filter)

        # Create config record
        self._config = await self._create_config(config_name)
        # Store build metadata for subsequent steps
        self._config.attributes = {
            **(self._config.attributes or {}),
            "build_state": {
                "completed_steps": [1],
                "plant_filter": plant_filter,
                "company_filter": company_filter,
            },
        }
        await self.db.flush()
        await self.db.commit()

        result = StepResult(
            step=1,
            step_name=STEP_NAMES[1],
            entity_type=STEP_ENTITY_TYPES[1],
            config_id=self._config.id,
            completed_steps=[1],
        )

        # Build table inventory
        for table_name, df in self._data.items():
            status = "available"
            if table_name.startswith("Z") or table_name.startswith("z"):
                status = "z_table"
            elif table_name not in KNOWN_SAP_TABLES:
                status = "custom"
            result.table_inventory.append({
                "table_name": table_name,
                "row_count": len(df),
                "columns": list(df.columns)[:20],
                "status": status,
            })

        # Validate required tables
        preview = ConfigPreview()
        self._validate_required_tables(preview)
        result.warnings = preview.warnings

        # Detect anomalies for validation step
        result.anomalies = self._detect_validation_anomalies()

        # Detect Z-tables
        result.z_tables = self._detect_z_tables()

        result.entities_created = 1  # the config record

        return result

    async def build_step(
        self,
        config_id: int,
        step: int,
        sap_data: Dict[str, pd.DataFrame],
        plant_filter: Optional[List[str]] = None,
        company_filter: Optional[str] = None,
        master_type_overrides: Optional[Dict[str, str]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> StepResult:
        """
        Execute a single build step for an existing config.

        Reloads data and existing entities, then executes only the
        requested step. Commits after execution.
        """
        self._data = sap_data
        self._apply_filters(plant_filter, company_filter)

        # Load existing config and entities
        await self._load_existing_entities(config_id)

        overrides = master_type_overrides or {}
        opts = options or {}

        result = StepResult(
            step=step,
            step_name=STEP_NAMES.get(step, f"Step {step}"),
            entity_type=STEP_ENTITY_TYPES.get(step, "unknown"),
            config_id=config_id,
        )

        # Execute the requested step
        if step == 2:
            count = await self._step_geography(result)
        elif step == 3:
            count = await self._step_sites(result, overrides)
        elif step == 4:
            count = await self._step_products(result)
        elif step == 5:
            count = await self._step_partners(result)
        elif step == 6:
            count = await self._step_bom(result)
        elif step == 7:
            count = await self._step_planning(result, opts)
        elif step == 8:
            count = await self._step_transactional(result, opts)
        elif step == 9:
            count = await self._step_lanes(result)
        else:
            result.warnings.append(f"Unknown step {step}")
            count = 0

        result.entities_created = count

        # Update build state
        build_state = (self._config.attributes or {}).get("build_state", {})
        completed = build_state.get("completed_steps", [1])
        if step not in completed:
            completed.append(step)
            completed.sort()
        build_state["completed_steps"] = completed
        attrs = dict(self._config.attributes or {})
        attrs["build_state"] = build_state
        self._config.attributes = attrs
        await self.db.flush()
        await self.db.commit()

        result.completed_steps = completed
        return result

    async def build_remaining(
        self,
        config_id: int,
        sap_data: Dict[str, pd.DataFrame],
        plant_filter: Optional[List[str]] = None,
        company_filter: Optional[str] = None,
        master_type_overrides: Optional[Dict[str, str]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute all remaining steps for an existing config.

        Checks which steps are already completed and runs the rest.
        """
        self._data = sap_data
        self._apply_filters(plant_filter, company_filter)
        await self._load_existing_entities(config_id)

        overrides = master_type_overrides or {}
        opts = options or {}

        build_state = (self._config.attributes or {}).get("build_state", {})
        completed = set(build_state.get("completed_steps", [1]))

        summary = {}
        for step_num in range(2, 10):
            if step_num in completed:
                continue
            result = StepResult(
                step=step_num,
                step_name=STEP_NAMES.get(step_num, ""),
                entity_type=STEP_ENTITY_TYPES.get(step_num, ""),
            )
            if step_num == 2:
                summary["geography"] = await self._step_geography(result)
            elif step_num == 3:
                summary["sites"] = await self._step_sites(result, overrides)
            elif step_num == 4:
                summary["products"] = await self._step_products(result)
            elif step_num == 5:
                summary["partners"] = await self._step_partners(result)
            elif step_num == 6:
                summary["bom"] = await self._step_bom(result)
            elif step_num == 7:
                summary["planning"] = await self._step_planning(result, opts)
            elif step_num == 8:
                summary["transactional"] = await self._step_transactional(result, opts)
            elif step_num == 9:
                summary["lanes"] = await self._step_lanes(result)
            completed.add(step_num)

        # Finalize
        build_state["completed_steps"] = sorted(completed)
        attrs = dict(self._config.attributes or {})
        attrs["build_state"] = build_state
        self._config.attributes = attrs
        await self.db.flush()
        await self.db.commit()

        return {
            "config_id": config_id,
            "config_name": self._config.name,
            "summary": summary,
        }

    async def analyze_z_table_deep(
        self,
        table_name: str,
        sap_data: Dict[str, pd.DataFrame],
    ) -> Dict[str, Any]:
        """
        Deep analysis of a single Z-table using the SAPFieldMappingService.

        Calls the AI-powered analysis endpoint for semantic understanding
        of the table's purpose and per-field mapping with confidence scores.
        """
        df = sap_data.get(table_name)
        if df is None or df.empty:
            return {"error": f"Table {table_name} not found or empty"}

        # Build field list for the field mapping service
        fields = [
            {"name": col, "type": str(df[col].dtype), "description": ""}
            for col in df.columns
        ]

        # Use the full AI-powered analysis from SAPFieldMappingService
        analysis = await self._field_mapping_service.analyze_z_table(
            table_name=table_name,
            table_description=f"Custom SAP table with {len(df)} rows",
            fields=fields,
            use_ai=True,
        )

        return {
            "table_name": analysis.table_name,
            "description": analysis.description,
            "suggested_entity": analysis.suggested_entity,
            "entity_confidence": analysis.entity_confidence,
            "field_count": analysis.field_count,
            "z_field_count": analysis.z_field_count,
            "field_mappings": [fm.to_dict() for fm in analysis.field_mappings],
            "mappable_fields": analysis.mappable_fields,
            "mapped_fields": analysis.mapped_fields,
            "unmapped_required": analysis.unmapped_required,
            "ai_purpose_analysis": analysis.ai_purpose_analysis,
            "ai_integration_guidance": analysis.ai_integration_guidance,
            "sample_data": df.head(5).to_dict(orient="records"),
        }

    async def get_build_status(self, config_id: int) -> Dict[str, Any]:
        """Get current build status for a config."""
        stmt = select(SupplyChainConfig).where(SupplyChainConfig.id == config_id)
        result = await self.db.execute(stmt)
        config = result.scalar_one_or_none()
        if not config:
            return {"error": f"Config {config_id} not found"}

        build_state = (config.attributes or {}).get("build_state", {})

        # Count entities
        entity_counts = {}
        for model, label in [
            (Site, "sites"), (Product, "products"),
            (TransportationLane, "lanes"), (TradingPartner, "partners"),
            (ProductBom, "bom_entries"), (Forecast, "forecasts"),
            (InvLevel, "inventory"), (Geography, "geography"),
            (SourcingRules, "sourcing_rules"),
        ]:
            stmt = select(model).where(model.config_id == config_id)
            rows = await self.db.execute(stmt)
            entity_counts[label] = len(rows.all())

        return {
            "config_id": config_id,
            "config_name": config.name,
            "completed_steps": build_state.get("completed_steps", []),
            "entity_counts": entity_counts,
            "created_at": config.created_at.isoformat() if hasattr(config, "created_at") and config.created_at else None,
        }

    async def delete_build(self, config_id: int) -> bool:
        """Delete a config and all its child entities."""
        stmt = select(SupplyChainConfig).where(SupplyChainConfig.id == config_id)
        result = await self.db.execute(stmt)
        config = result.scalar_one_or_none()
        if not config:
            return False

        # Delete child entities in reverse dependency order
        # Only delete models that have a config_id column (TradingPartner,
        # VendorProduct, VendorLeadTime don't — they reference shared entities)
        from sqlalchemy import delete as sql_delete

        # Transactional entities first (depend on products/sites)
        await self.db.execute(sql_text(
            "DELETE FROM inbound_order_line WHERE config_id = :cid"), {"cid": config_id})
        await self.db.execute(sql_delete(InboundOrder).where(InboundOrder.config_id == config_id))
        await self.db.execute(sql_text(
            "DELETE FROM production_order_components WHERE production_order_id IN "
            "(SELECT id FROM production_orders WHERE config_id = :cid)"), {"cid": config_id})
        await self.db.execute(sql_delete(ProductionOrder).where(ProductionOrder.config_id == config_id))
        await self.db.execute(sql_delete(OutboundOrderLine).where(OutboundOrderLine.config_id == config_id))
        await self.db.execute(sql_delete(OutboundOrder).where(OutboundOrder.config_id == config_id))

        for model in [
            Forecast, InvLevel, InvPolicy, SourcingRules,
            ProductBom, ProductionProcess,
            TransportationLane, Product, Market, Site,
        ]:
            await self.db.execute(
                sql_delete(model).where(model.config_id == config_id)
            )
        # Geography uses string PK prefixed with config_id
        await self.db.execute(
            sql_delete(Geography).where(Geography.id.like(f"{config_id}_%"))
        )

        await self.db.delete(config)
        await self.db.commit()
        logger.info(f"Deleted config {config_id} and all child entities")
        return True

    # ------------------------------------------------------------------
    # Individual Step Executors (for step-by-step mode)
    # ------------------------------------------------------------------

    async def _step_geography(self, result: StepResult) -> int:
        """Execute step 2: Geography."""
        adrc = self._data.get("ADRC", pd.DataFrame())
        if adrc.empty:
            result.warnings.append("No ADRC address data available — geography step skipped")
            return 0

        await self._create_geography()
        count = len(adrc)

        # Sample data
        for _, row in adrc.head(10).iterrows():
            result.sample_data.append({
                "address_id": str(row.get("ADDRNUMBER", "")),
                "city": str(row.get("CITY1", "")),
                "country": str(row.get("COUNTRY", "")),
                "region": str(row.get("REGION", "")),
            })

        # Anomaly detection
        result.anomalies = self._detect_geography_anomalies(adrc)
        return count

    async def _step_sites(self, result: StepResult, overrides: Dict[str, str]) -> int:
        """Execute step 3: Sites."""
        count = await self._create_sites(overrides)

        # Sample data
        for key, site in list(self._sites.items())[:10]:
            result.sample_data.append({
                "key": key,
                "name": site.type,
                "master_type": site.master_type,
                "dag_type": site.dag_type,
            })

        result.anomalies = self._detect_site_anomalies()
        return count

    async def _step_products(self, result: StepResult) -> int:
        """Execute step 4: Products."""
        count = await self._create_products()

        # Sample data
        for key, prod in list(self._products.items())[:10]:
            result.sample_data.append({
                "material": key,
                "description": prod.description,
                "category": prod.category or "",
            })

        result.anomalies = self._detect_product_anomalies()
        return count

    async def _step_lanes(self, result: StepResult) -> int:
        """Execute step 5: Transportation Lanes."""
        count = await self._create_lanes()

        # Sample data from preview
        preview = ConfigPreview()
        lane_previews = self._infer_lanes(preview)
        for lp in lane_previews[:10]:
            result.sample_data.append({
                "from": lp.from_key,
                "to": lp.to_key,
                "source": lp.source,
                "lead_time_days": lp.lead_time_days,
            })
        result.warnings = preview.warnings

        result.anomalies = self._detect_lane_anomalies(lane_previews)
        return count

    async def _step_partners(self, result: StepResult) -> int:
        """Execute step 6: Partners & Sourcing."""
        vendor_count, customer_count, sourcing_count = await self._create_partners_and_sourcing()
        total = vendor_count + customer_count + sourcing_count

        # Sample data
        lfa1 = self._data.get("LFA1", pd.DataFrame())
        if not lfa1.empty:
            for _, row in lfa1.head(5).iterrows():
                result.sample_data.append({
                    "type": "vendor",
                    "id": str(row.get("LIFNR", "")),
                    "name": str(row.get("NAME1", "")),
                })
        kna1 = self._data.get("KNA1", pd.DataFrame())
        if not kna1.empty:
            for _, row in kna1.head(5).iterrows():
                result.sample_data.append({
                    "type": "customer",
                    "id": str(row.get("KUNNR", "")),
                    "name": str(row.get("NAME1", "")),
                })

        result.anomalies = self._detect_partner_anomalies()
        return total

    async def _step_bom(self, result: StepResult) -> int:
        """Execute step 7: BOM & Manufacturing."""
        count = await self._create_bom_and_manufacturing()

        # Sample data
        stpo = self._data.get("STPO", pd.DataFrame())
        if not stpo.empty:
            for _, row in stpo.head(10).iterrows():
                result.sample_data.append({
                    "bom_number": str(row.get("STLNR", "")),
                    "component": str(row.get("IDNRK", "")),
                    "quantity": str(row.get("MENGE", "")),
                })

        result.anomalies = self._detect_bom_anomalies()
        return count

    async def _step_planning(self, result: StepResult, opts: Dict[str, Any]) -> int:
        """Execute step 8: Planning Data."""
        forecast_count = 0
        inv_count = 0
        spc_count = 0
        if opts.get("include_forecasts", True):
            forecast_count = await self._create_forecasts(
                horizon_weeks=opts.get("forecast_horizon_weeks", 52)
            )
        if opts.get("include_inventory", True):
            inv_count = await self._create_inventory(
                default_policy=opts.get("default_inv_policy", "doc_dem"),
                safety_days=opts.get("default_safety_days", 14),
            )
            spc_count = await self._create_site_planning_configs()

        result.sample_data.append({
            "forecasts_created": forecast_count,
            "inventory_records_created": inv_count,
            "site_planning_configs_created": spc_count,
            "policy_type": opts.get("default_inv_policy", "doc_dem"),
            "safety_days": opts.get("default_safety_days", 14),
        })

        result.anomalies = self._detect_planning_anomalies()
        return forecast_count + inv_count + spc_count

    async def _create_site_planning_configs(self) -> int:
        """Create SitePlanningConfig rows from SAP MARC data.

        Persists the MRP planning parameters (DISMM, DISLS, VRMOD, FXHOR, etc.)
        that were previously extracted but never stored.  These drive the digital
        twin's heuristic dispatch — see DIGITAL_TWIN.md §8A and §8C.
        """
        from app.models.site_planning_config import (
            SitePlanningConfig, SAP_DISMM_MAP, SAP_DISLS_MAP, PlanningMethod, LotSizingRule,
        )

        marc = self._data.get("MARC", pd.DataFrame())
        if marc.empty:
            logger.info("No MARC data — skipping site_planning_config creation")
            return 0

        count = 0
        prefix = f"CFG{self._config.id}_"
        tenant_id = getattr(self._config, "tenant_id", None)
        if tenant_id is None:
            logger.warning("Config has no tenant_id — skipping site_planning_config")
            return 0

        for _, row in marc.iterrows():
            mat_key = str(row.get("MATNR", "")).strip()
            site_key = str(row.get("WERKS", "")).strip()

            if mat_key not in self._products or site_key not in self._sites:
                continue

            product_id = f"{prefix}{mat_key}"
            site_id = self._sites[site_key].id

            dismm = str(row.get("DISMM", "")).strip()
            disls = str(row.get("DISLS", "")).strip()

            spc = SitePlanningConfig(
                config_id=self._config.id,
                tenant_id=tenant_id,
                site_id=site_id,
                product_id=product_id,
                planning_method=SAP_DISMM_MAP.get(dismm, PlanningMethod.REORDER_POINT.value),
                lot_sizing_rule=SAP_DISLS_MAP.get(disls, LotSizingRule.LOT_FOR_LOT.value),
                fixed_lot_size=float(pd.to_numeric(row.get("LOSGR", 0), errors="coerce") or 0) or None,
                min_order_quantity=float(pd.to_numeric(row.get("BSTMI", 0), errors="coerce") or 0) or None,
                max_order_quantity=float(pd.to_numeric(row.get("BSTMA", 0), errors="coerce") or 0) or None,
                order_multiple=float(pd.to_numeric(row.get("BSTRF", 0), errors="coerce") or 0) or None,
                frozen_horizon_days=int(pd.to_numeric(row.get("FXHOR", 0), errors="coerce") or 0) or None,
                forecast_consumption_mode=str(row.get("VRMOD", "")).strip() or None,
                forecast_consumption_fwd_days=int(pd.to_numeric(row.get("VINT1", 0), errors="coerce") or 0) or None,
                forecast_consumption_bwd_days=int(pd.to_numeric(row.get("VINT2", 0), errors="coerce") or 0) or None,
                procurement_type=str(row.get("BESKZ", "")).strip() or None,
                strategy_group=str(row.get("STRGR", "")).strip() or None,
                mrp_controller=str(row.get("DISPO", "")).strip() or None,
                erp_source="SAP",
                erp_params={
                    k: v for k, v in {
                        "DISMM": dismm, "DISLS": disls,
                        "LOSGR": float(pd.to_numeric(row.get("LOSGR", 0), errors="coerce") or 0),
                        "VRMOD": str(row.get("VRMOD", "")).strip(),
                        "VINT1": int(pd.to_numeric(row.get("VINT1", 0), errors="coerce") or 0),
                        "VINT2": int(pd.to_numeric(row.get("VINT2", 0), errors="coerce") or 0),
                        "FXHOR": int(pd.to_numeric(row.get("FXHOR", 0), errors="coerce") or 0),
                        "STRGR": str(row.get("STRGR", "")).strip(),
                        "BESKZ": str(row.get("BESKZ", "")).strip(),
                        "DISPO": str(row.get("DISPO", "")).strip(),
                    }.items() if v  # omit empty/zero values
                },
            )
            self.db.add(spc)
            count += 1

        await self.db.flush()
        logger.info(f"Created {count} site_planning_config records from MARC")
        return count

    # ------------------------------------------------------------------
    # Entity Reload (for stateless step-by-step mode)
    # ------------------------------------------------------------------

    async def _load_existing_entities(self, config_id: int):
        """Load existing config and entities from DB for incremental building."""
        # Load config
        stmt = select(SupplyChainConfig).where(SupplyChainConfig.id == config_id)
        result = await self.db.execute(stmt)
        self._config = result.scalar_one_or_none()
        if not self._config:
            raise ValueError(f"Config {config_id} not found")

        # Load existing sites
        stmt = select(Site).where(Site.config_id == config_id)
        result = await self.db.execute(stmt)
        for site in result.scalars().all():
            sap_key = (site.attributes or {}).get("sap_plant_code", site.name)
            self._sites[sap_key] = site

        # Load existing products
        prefix = f"CFG{config_id}_"
        stmt = select(Product).where(Product.config_id == config_id)
        result = await self.db.execute(stmt)
        for product in result.scalars().all():
            mat_key = product.id.replace(prefix, "") if product.id.startswith(prefix) else product.id
            self._products[mat_key] = product

    # ------------------------------------------------------------------
    # Z-Table Detection
    # ------------------------------------------------------------------

    def _detect_z_tables(self) -> List[Dict[str, Any]]:
        """Detect Z-tables and unknown custom tables in loaded data.

        Uses SAPFieldMappingService for fuzzy matching of individual fields
        to provide per-field mapping suggestions with confidence scores.
        """
        z_tables = []
        for table_name, df in self._data.items():
            if df.empty:
                continue
            is_z = table_name.upper().startswith("Z") or table_name.upper().startswith("/Z")
            is_unknown = table_name not in KNOWN_SAP_TABLES and not is_z
            if is_z or is_unknown:
                # Use field mapping service for per-field fuzzy matching
                field_mappings = self._fuzzy_match_fields(df)

                # Infer entity from field mappings (count which entity gets most matches)
                suggested_entity = self._infer_entity_from_field_mappings(field_mappings)

                # Summarize field mapping quality
                high_conf = sum(1 for fm in field_mappings if fm["confidence"] == "high")
                medium_conf = sum(1 for fm in field_mappings if fm["confidence"] == "medium")
                low_conf = sum(1 for fm in field_mappings if fm["confidence"] == "low")

                z_tables.append({
                    "table_name": table_name,
                    "row_count": len(df),
                    "field_count": len(df.columns),
                    "columns": list(df.columns)[:30],
                    "is_z_table": is_z,
                    "suggested_entity": suggested_entity,
                    "field_mappings": field_mappings[:20],  # top 20 field mappings
                    "mapping_summary": {
                        "high_confidence": high_conf,
                        "medium_confidence": medium_conf,
                        "low_confidence": low_conf,
                        "unmapped": len(df.columns) - high_conf - medium_conf - low_conf,
                    },
                    "ai_rationale": (
                        f"Fuzzy matching found {high_conf} high-confidence, "
                        f"{medium_conf} medium-confidence field mappings "
                        f"out of {len(df.columns)} fields"
                    ),
                })
        return z_tables

    def _fuzzy_match_fields(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Use SAPFieldMappingService to fuzzy-match each column in a DataFrame.

        Runs synchronous pattern + fuzzy matching (no AI calls) for speed.
        """
        results = []
        svc = self._field_mapping_service

        for col_name in df.columns:
            # Pattern match first (fast, regex-based)
            pattern_match = svc._match_by_pattern(col_name)
            if pattern_match:
                entity, field_name, score = pattern_match
                results.append({
                    "sap_field": col_name,
                    "is_z_field": svc._is_z_field(col_name),
                    "aws_sc_entity": entity if entity != "*" else None,
                    "aws_sc_field": field_name,
                    "confidence": "high" if score >= 0.9 else "medium",
                    "confidence_score": round(score, 3),
                    "match_source": "pattern",
                })
                continue

            # Fuzzy match against all AWS SC fields
            best_score = 0.0
            best_entity = None
            best_field = None

            from app.services.sap_field_mapping_service import AWS_SC_FIELDS
            for entity, entity_fields in AWS_SC_FIELDS.items():
                for aws_field, field_info in entity_fields.items():
                    score = svc._combined_similarity(
                        col_name, aws_field, "", field_info.get("description", "")
                    )
                    if score > best_score:
                        best_score = score
                        best_entity = entity
                        best_field = aws_field

            if best_score >= 0.5:
                if best_score >= 0.9:
                    conf = "high"
                elif best_score >= 0.7:
                    conf = "medium"
                else:
                    conf = "low"
                results.append({
                    "sap_field": col_name,
                    "is_z_field": svc._is_z_field(col_name),
                    "aws_sc_entity": best_entity,
                    "aws_sc_field": best_field,
                    "confidence": conf,
                    "confidence_score": round(best_score, 3),
                    "match_source": "fuzzy",
                })
            else:
                results.append({
                    "sap_field": col_name,
                    "is_z_field": svc._is_z_field(col_name),
                    "aws_sc_entity": None,
                    "aws_sc_field": None,
                    "confidence": "none",
                    "confidence_score": round(best_score, 3),
                    "match_source": "none",
                })

        return results

    def _infer_entity_from_field_mappings(
        self, field_mappings: List[Dict[str, Any]]
    ) -> Optional[str]:
        """Infer the most likely entity type from aggregated field mappings."""
        entity_scores: Dict[str, float] = {}
        for fm in field_mappings:
            entity = fm.get("aws_sc_entity")
            if not entity:
                continue
            score = fm.get("confidence_score", 0)
            entity_scores[entity] = entity_scores.get(entity, 0) + score

        if not entity_scores:
            return None
        return max(entity_scores, key=entity_scores.get)

    # ------------------------------------------------------------------
    # Anomaly Detection (per step)
    # ------------------------------------------------------------------

    def _detect_validation_anomalies(self) -> List[Dict[str, Any]]:
        """Detect anomalies during validation step."""
        anomalies = []

        # Check for required tables
        for table in ["MARA", "T001W"]:
            if table not in self._data or self._data[table].empty:
                if table == "MARA" and "MARC" in self._data and not self._data["MARC"].empty:
                    continue
                anomalies.append({
                    "severity": "error",
                    "message": f"Required table {table} is missing or empty",
                    "suggested_action": f"Ensure {table} CSV file is present in the connection directory",
                    "affected_entity": table,
                })

        # Check for very small datasets
        for table_name, df in self._data.items():
            if not df.empty and len(df) < 5:
                anomalies.append({
                    "severity": "warning",
                    "message": f"Table {table_name} has only {len(df)} rows — may be incomplete",
                    "suggested_action": f"Verify that {table_name} export is complete",
                    "affected_entity": table_name,
                })

        # Check for empty key columns
        key_checks = [
            ("MARA", "MATNR"), ("T001W", "WERKS"), ("LFA1", "LIFNR"), ("KNA1", "KUNNR"),
        ]
        for table, col in key_checks:
            df = self._data.get(table, pd.DataFrame())
            if not df.empty and col in df.columns:
                nulls = df[col].isna().sum()
                if nulls > 0:
                    anomalies.append({
                        "severity": "warning",
                        "message": f"{table}.{col} has {nulls} null values",
                        "suggested_action": f"Check {table} data quality — null key fields will be skipped",
                        "affected_entity": f"{table}.{col}",
                    })

        return anomalies

    def _detect_geography_anomalies(self, adrc: pd.DataFrame) -> List[Dict[str, Any]]:
        """Detect anomalies in geography data."""
        anomalies = []

        if "COUNTRY" in adrc.columns:
            missing_country = adrc["COUNTRY"].isna().sum() + (adrc["COUNTRY"] == "").sum()
            if missing_country > 0:
                anomalies.append({
                    "severity": "warning",
                    "message": f"{missing_country} addresses have no country code",
                    "suggested_action": "Review ADRC records and add missing country codes",
                    "affected_entity": "ADRC.COUNTRY",
                })

        if "CITY1" in adrc.columns:
            missing_city = adrc["CITY1"].isna().sum() + (adrc["CITY1"] == "").sum()
            if missing_city > 0:
                anomalies.append({
                    "severity": "info",
                    "message": f"{missing_city} addresses have no city",
                    "suggested_action": "City is optional but improves geographic grouping",
                    "affected_entity": "ADRC.CITY1",
                })

        return anomalies

    def _detect_site_anomalies(self) -> List[Dict[str, Any]]:
        """Detect anomalies in site inference."""
        anomalies = []
        marc = self._data.get("MARC", pd.DataFrame())

        for key, site in self._sites.items():
            attrs = site.attributes or {}
            product_count = attrs.get("product_count", 0)

            if product_count == 0 and not site.is_external:
                anomalies.append({
                    "severity": "warning",
                    "message": f"Site {key} ({site.type}) has 0 products assigned",
                    "suggested_action": "Check MARC data for this plant or consider excluding it",
                    "affected_entity": key,
                })

            # Check for ambiguous inference
            plants_with_bom = self._get_plants_with_bom()
            vendor_plants = self._get_vendor_plant_codes()
            customer_sites = self._get_customer_ship_to_sites()
            matches = 0
            if key in plants_with_bom:
                matches += 1
            if key in vendor_plants:
                matches += 1
            if key in customer_sites:
                matches += 1
            if matches > 1:
                anomalies.append({
                    "severity": "info",
                    "message": f"Site {key} matches multiple master types — inferred as {site.master_type}",
                    "suggested_action": "Consider overriding the master type if the inference is incorrect",
                    "affected_entity": key,
                })

        return anomalies

    def _detect_product_anomalies(self) -> List[Dict[str, Any]]:
        """Detect anomalies in product creation."""
        anomalies = []
        mara = self._data.get("MARA", pd.DataFrame())

        if not mara.empty and "MAKTX" in mara.columns:
            missing_desc = mara["MAKTX"].isna().sum() + (mara["MAKTX"].astype(str).str.strip() == "").sum()
            if missing_desc > 0:
                anomalies.append({
                    "severity": "warning",
                    "message": f"{missing_desc} materials have no description (MAKTX)",
                    "suggested_action": "Materials without descriptions will use the material number as name",
                    "affected_entity": "MARA.MAKTX",
                })

        if not mara.empty and "MEINS" in mara.columns:
            missing_uom = mara["MEINS"].isna().sum() + (mara["MEINS"].astype(str).str.strip() == "").sum()
            if missing_uom > 0:
                anomalies.append({
                    "severity": "info",
                    "message": f"{missing_uom} materials have no base UOM — defaulting to EA",
                    "suggested_action": "Add MARM UOM conversion data for accurate unit handling",
                    "affected_entity": "MARA.MEINS",
                })

        return anomalies

    def _detect_lane_anomalies(self, lane_previews: List[LanePreview]) -> List[Dict[str, Any]]:
        """Detect anomalies in transportation lane inference."""
        anomalies = []

        # Count lanes by source
        source_counts: Dict[str, int] = {}
        no_lead_time = 0
        missing_endpoint = 0
        for lp in lane_previews:
            source_counts[lp.source] = source_counts.get(lp.source, 0) + 1
            if lp.lead_time_days == 0:
                no_lead_time += 1
            if lp.from_key not in self._sites or lp.to_key not in self._sites:
                missing_endpoint += 1

        if no_lead_time > 0:
            anomalies.append({
                "severity": "warning",
                "message": f"{no_lead_time} lanes have no lead time data — defaulting to 7 days",
                "suggested_action": "Add EINE (Purchasing Info) data for vendor lead times",
                "affected_entity": "transportation_lane",
            })

        if missing_endpoint > 0:
            anomalies.append({
                "severity": "info",
                "message": f"{missing_endpoint} inferred lanes have endpoints not in site list — skipped",
                "suggested_action": "These are vendor/customer codes not registered as sites",
                "affected_entity": "transportation_lane",
            })

        # Warn about low-confidence sources
        delivery_only = source_counts.get("delivery_history", 0)
        ekpo_only = source_counts.get("ekpo_history", 0)
        if delivery_only + ekpo_only > 0 and source_counts.get("apo_trlane", 0) == 0:
            anomalies.append({
                "severity": "warning",
                "message": f"{delivery_only + ekpo_only} lanes inferred from transaction history (lower confidence)",
                "suggested_action": "For higher accuracy, provide APO TRLANE or EORD source list data",
                "affected_entity": "transportation_lane",
            })

        return anomalies

    def _detect_partner_anomalies(self) -> List[Dict[str, Any]]:
        """Detect anomalies in partner/sourcing data."""
        anomalies = []

        eord = self._data.get("EORD", pd.DataFrame())
        eina = self._data.get("EINA", pd.DataFrame())
        eine = self._data.get("EINE", pd.DataFrame())

        if eord.empty:
            anomalies.append({
                "severity": "warning",
                "message": "No source list (EORD) data — sourcing rules not created",
                "suggested_action": "Add EORD data to define approved vendor-plant assignments",
                "affected_entity": "sourcing_rules",
            })

        if eina.empty:
            anomalies.append({
                "severity": "info",
                "message": "No purchasing info records (EINA/EINE) — vendor pricing not available",
                "suggested_action": "Add EINA/EINE for vendor pricing and MOQ data",
                "affected_entity": "vendor_product",
            })
        elif not eine.empty and "NETPR" in eine.columns:
            zero_price = (pd.to_numeric(eine["NETPR"], errors="coerce").fillna(0) == 0).sum()
            if zero_price > 0:
                anomalies.append({
                    "severity": "info",
                    "message": f"{zero_price} purchasing info records have zero net price",
                    "suggested_action": "Zero-price records may indicate framework agreements — review if pricing is needed",
                    "affected_entity": "EINE.NETPR",
                })

        return anomalies

    def _detect_bom_anomalies(self) -> List[Dict[str, Any]]:
        """Detect anomalies in BOM/manufacturing data."""
        anomalies = []
        stpo = self._data.get("STPO", pd.DataFrame())
        stko = self._data.get("STKO", pd.DataFrame())

        if stpo.empty:
            anomalies.append({
                "severity": "info",
                "message": "No BOM data (STPO) — no bill of materials created",
                "suggested_action": "Add STPO/STKO for BOM structures",
                "affected_entity": "product_bom",
            })
            return anomalies

        # Check for components not in product master
        if "IDNRK" in stpo.columns:
            component_keys = set(stpo["IDNRK"].astype(str).str.strip().unique())
            missing = component_keys - set(self._products.keys())
            if missing:
                anomalies.append({
                    "severity": "warning",
                    "message": f"{len(missing)} BOM components not found in product master",
                    "suggested_action": "These components will be skipped — ensure MARA includes all BOM materials",
                    "affected_entity": "product_bom",
                })

        # Missing header data
        if stko.empty:
            anomalies.append({
                "severity": "info",
                "message": "No BOM headers (STKO) — base quantities default to 1.0",
                "suggested_action": "Add STKO for accurate base quantity and BOM validity dates",
                "affected_entity": "STKO",
            })

        return anomalies

    def _detect_planning_anomalies(self) -> List[Dict[str, Any]]:
        """Detect anomalies in planning data."""
        anomalies = []

        snpfc = self._data.get("/SAPAPO/SNPFC", pd.DataFrame())
        snpbv = self._data.get("/SAPAPO/SNPBV", pd.DataFrame())
        mard = self._data.get("MARD", pd.DataFrame())

        if snpfc.empty and snpbv.empty:
            anomalies.append({
                "severity": "warning",
                "message": "No forecast data (SNPFC/SNPBV) — forecasts not created",
                "suggested_action": "Add APO forecast data for demand planning baseline",
                "affected_entity": "forecast",
            })

        if mard.empty:
            anomalies.append({
                "severity": "warning",
                "message": "No inventory data (MARD) — initial inventory levels not set",
                "suggested_action": "Add MARD data for initial inventory snapshots",
                "affected_entity": "inv_level",
            })
        elif "LABST" in mard.columns:
            zero_inv = (pd.to_numeric(mard["LABST"], errors="coerce").fillna(0) == 0).sum()
            total = len(mard)
            if zero_inv > total * 0.5:
                anomalies.append({
                    "severity": "info",
                    "message": f"{zero_inv}/{total} storage locations have zero inventory",
                    "suggested_action": "High proportion of zero inventory may indicate stale MARD data",
                    "affected_entity": "MARD.LABST",
                })

        return anomalies

    # ------------------------------------------------------------------
    # Step 1: Validation
    # ------------------------------------------------------------------

    def _validate_required_tables(self, preview: ConfigPreview):
        """Check that minimum required tables are present."""
        required = ["MARA", "T001W"]
        for table in required:
            if table not in self._data or self._data[table].empty:
                # Also check MARC as fallback for material data
                if table == "MARA" and "MARC" in self._data and not self._data["MARC"].empty:
                    continue
                preview.warnings.append(f"Required table {table} is missing or empty")

    def _apply_filters(
        self,
        plant_filter: Optional[List[str]],
        company_filter: Optional[str],
    ):
        """Apply plant and company filters to all DataFrames.

        T001W does not have a BUKRS column — the company→plant mapping in SAP
        goes through T001K (valuation area).  Since T001K is often absent in
        CSV exports, we derive the plant whitelist from T001.LAND1: plants in
        T001W whose LAND1 matches the target company's LAND1 belong to that
        country template.  This correctly handles IDES FAA exports where all
        country-template plants appear in the same T001W CSV.
        """
        if not plant_filter and not company_filter:
            return

        # Build plant whitelist from company filter via T001 country matching
        effective_plant_filter: Optional[set] = set(plant_filter) if plant_filter else None

        if company_filter:
            t001 = self._data.get("T001", pd.DataFrame())
            t001w = self._data.get("T001W", pd.DataFrame())
            if not t001.empty and not t001w.empty:
                # Find the company's country code
                bukrs_col = next((c for c in ["BUKRS", "bukrs"] if c in t001.columns), None)
                land1_col_t001 = next((c for c in ["LAND1", "land1"] if c in t001.columns), None)
                if bukrs_col and land1_col_t001:
                    company_rows = t001[t001[bukrs_col].astype(str).str.strip() == company_filter]
                    if not company_rows.empty:
                        company_land1 = str(company_rows.iloc[0][land1_col_t001]).strip()
                        land1_col_w = next((c for c in ["LAND1", "land1"] if c in t001w.columns), None)
                        werks_col_w = next((c for c in ["WERKS", "werks"] if c in t001w.columns), None)
                        if land1_col_w and werks_col_w and company_land1:
                            matching_plants = set(
                                t001w[t001w[land1_col_w].astype(str).str.strip() == company_land1][werks_col_w]
                                .astype(str).str.strip().tolist()
                            )
                            if matching_plants:
                                if effective_plant_filter is not None:
                                    effective_plant_filter &= matching_plants
                                else:
                                    effective_plant_filter = matching_plants

        for table_name, df in list(self._data.items()):
            if df.empty:
                continue
            filtered = df
            if effective_plant_filter and "WERKS" in df.columns:
                filtered = filtered[filtered["WERKS"].astype(str).str.strip().isin(effective_plant_filter)]
            if company_filter and "BUKRS" in df.columns:
                filtered = filtered[filtered["BUKRS"].astype(str).str.strip() == company_filter]
            self._data[table_name] = filtered

    # ------------------------------------------------------------------
    # Step 2: Company & Geography
    # ------------------------------------------------------------------

    async def _create_geography(self, geocoding_callback=None):
        """Create Geography entities from ADRC addresses (upsert, deduplicated).

        Two-phase approach:
        1. Insert geography rows immediately WITHOUT coordinates (fast)
        2. Return a coroutine for geocoding that can run in parallel with other steps

        Returns:
            An awaitable that performs geocoding and updates geography rows with
            coordinates, or None if no geocoding is needed.
        """
        adrc = self._data.get("ADRC", pd.DataFrame())
        if adrc.empty:
            return None

        from sqlalchemy.dialects.postgresql import insert as pg_insert

        geo_df = self.mapper.map_geography(adrc)

        def _clean(val) -> str:
            """Convert value to string, treating NaN/None as empty."""
            if val is None:
                return ""
            s = str(val).strip()
            if s.lower() in ("nan", "none", "null", "na", "n/a"):
                return ""
            return s

        # Deduplicate by id — last occurrence wins
        seen: Dict[str, dict] = {}
        for _, row in geo_df.iterrows():
            geo_id = _clean(row.get("address_id"))
            key = f"{self._config.id}_{geo_id}"
            seen[key] = {
                "id": key,
                "description": _clean(row.get("name")),
                "address_1": _clean(row.get("street")),
                "city": _clean(row.get("city")),
                "state_prov": _clean(row.get("region")),
                "country": _clean(row.get("country")),
                "postal_code": _clean(row.get("postal_code")),
            }

        rows = list(seen.values())

        # Phase 1: Insert geography rows immediately (no coordinates yet)
        if rows:
            for r in rows:
                r.setdefault("latitude", None)
                r.setdefault("longitude", None)
            # Batch insert to stay under PostgreSQL's 32767 parameter limit
            # (9 columns per row → max ~3600 rows per batch)
            BATCH_SIZE = 500
            for i in range(0, len(rows), BATCH_SIZE):
                batch = rows[i : i + BATCH_SIZE]
                stmt = pg_insert(Geography).values(batch)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "description": stmt.excluded.description,
                        "address_1": stmt.excluded.address_1,
                        "city": stmt.excluded.city,
                        "state_prov": stmt.excluded.state_prov,
                        "country": stmt.excluded.country,
                        "postal_code": stmt.excluded.postal_code,
                        "latitude": stmt.excluded.latitude,
                        "longitude": stmt.excluded.longitude,
                    },
                )
                await self.db.execute(stmt)
            await self.db.flush()
            logger.info(f"Inserted {len(rows)} geography records (coordinates pending)")

        # Phase 2: Return a coroutine for geocoding (runs in parallel with other steps)
        if not rows:
            return None

        async def _geocode_and_update():
            """Geocode addresses and UPDATE geography rows with coordinates.

            Uses its own DB session since this runs concurrently with other
            build steps that use the main session.
            """
            from app.services.geocoding_service import geocode_batch
            from app.db.session import async_session_factory

            def _loc_key(r):
                return (
                    r.get("city", "").strip().lower(),
                    r.get("state_prov", "").strip().lower(),
                    r.get("country", "").strip().lower(),
                )

            # Build unique location set
            unique_locs: Dict[tuple, dict] = {}
            for r in rows:
                key = _loc_key(r)
                if key not in unique_locs:
                    unique_locs[key] = {
                        "city": r.get("city", ""),
                        "state": r.get("state_prov", ""),
                        "country": r.get("country", ""),
                    }

            unique_inputs = list(unique_locs.values())
            logger.info(
                f"Geocoding {len(unique_inputs)} unique locations "
                f"(from {len(rows)} total addresses)"
            )

            def _addr_label(r):
                parts = [r.get("city", ""), r.get("state", ""), r.get("country", "")]
                return ", ".join(p.strip() for p in parts if p and p.strip()) or "Unknown"

            if geocoding_callback:
                import json as _json
                addr_labels = [_addr_label(a) for a in unique_inputs]
                await geocoding_callback(-1, len(unique_inputs), _json.dumps(addr_labels), "init")

            try:
                coords = await geocode_batch(unique_inputs, progress_callback=geocoding_callback)

                # Build lookup from unique key → coords
                coord_lookup: Dict[tuple, Tuple[float, float]] = {}
                for loc_dict, coord in zip(unique_inputs, coords):
                    if coord:
                        k = (
                            loc_dict["city"].strip().lower(),
                            loc_dict["state"].strip().lower(),
                            loc_dict["country"].strip().lower(),
                        )
                        coord_lookup[k] = coord

                # Update geography rows with coordinates using a separate session
                updates = []
                for row in rows:
                    c = coord_lookup.get(_loc_key(row))
                    if c:
                        updates.append({"geo_id": row["id"], "lat": c[0], "lon": c[1]})

                if updates:
                    from sqlalchemy import text as sql_text
                    async with async_session_factory() as geo_db:
                        for u in updates:
                            await geo_db.execute(
                                sql_text(
                                    "UPDATE geography SET latitude = :lat, longitude = :lon WHERE id = :gid"
                                ),
                                {"lat": u["lat"], "lon": u["lon"], "gid": u["geo_id"]},
                            )
                        await geo_db.commit()

                logger.info(f"Geocoded {len(updates)}/{len(rows)} geography records ({len(unique_inputs)} unique lookups)")
            except Exception as e:
                logger.warning(f"Geocoding batch failed, continuing without coordinates: {e}")

        return _geocode_and_update

    # Representative coordinates for regions/countries (ISO alpha-2 → lat, lon)
    _REGION_COORDS: Dict[str, Tuple[float, float]] = {
        # Countries
        "US": (39.8283, -98.5795), "CA": (56.1304, -106.3468),
        "MX": (23.6345, -102.5528), "BR": (-14.2350, -51.9253),
        "AR": (-38.4161, -63.6167), "CL": (-35.6751, -71.5430),
        "GB": (55.3781, -3.4360), "DE": (51.1657, 10.4515),
        "FR": (46.6034, 1.8883), "IT": (41.8719, 12.5674),
        "ES": (40.4637, -3.7492), "NL": (52.1326, 5.2913),
        "CH": (46.8182, 8.2275), "AT": (47.5162, 14.5501),
        "SE": (60.1282, 18.6435), "NO": (60.4720, 8.4689),
        "DK": (56.2639, 9.5018), "FI": (61.9241, 25.7482),
        "PL": (51.9194, 19.1451), "CZ": (49.8175, 15.4730),
        "BE": (50.5039, 4.4699), "PT": (39.3999, -8.2245),
        "IE": (53.1424, -7.6921), "RU": (61.5240, 105.3188),
        "CN": (35.8617, 104.1954), "JP": (36.2048, 138.2529),
        "KR": (35.9078, 127.7669), "IN": (20.5937, 78.9629),
        "TW": (23.6978, 120.9605), "SG": (1.3521, 103.8198),
        "TH": (15.8700, 100.9925), "VN": (14.0583, 108.2772),
        "MY": (4.2105, 101.9758), "ID": (-0.7893, 113.9213),
        "PH": (12.8797, 121.7740), "AU": (-25.2744, 133.7751),
        "NZ": (-40.9006, 174.8860), "ZA": (-30.5595, 22.9375),
        "NG": (9.0820, 8.6753), "EG": (26.8206, 30.8025),
        "KE": (-0.0236, 37.9062), "AE": (23.4241, 53.8478),
        "SA": (23.8859, 45.0792), "IL": (31.0461, 34.8516),
        "TR": (38.9637, 35.2433), "CO": (4.5709, -74.2973),
        "PE": (-9.1900, -75.0152),
        # Continents / aggregated regions
        "AMERICAS": (19.4326, -99.1332), "EUROPE": (50.1109, 8.6821),
        "ASIA": (34.0479, 100.6197), "AFRICA": (1.6508, 10.2679),
        "OCEANIA": (-25.2744, 133.7751), "OTHER": (0.0, 0.0),
        "NORTH_AMERICA": (39.8283, -98.5795),
        "SOUTH_AMERICA": (-14.2350, -51.9253),
    }

    async def _create_region_geographies(
        self, regions: Dict[str, dict],
    ) -> Dict[str, str]:
        """Create Geography records for regional market sites and return region_key → geo_id."""
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        result_map: Dict[str, str] = {}
        rows = []
        for region_key, info in regions.items():
            geo_id = f"{self._config.id}_REGION_{region_key}"
            coords = self._REGION_COORDS.get(region_key)
            # For single-country regions, try the country code
            if not coords and len(info.get("countries", [])) == 1:
                coords = self._REGION_COORDS.get(info["countries"][0])
            # For continent regions, try the continent name
            if not coords:
                continent = info.get("continent", "").upper().replace(" ", "_")
                coords = self._REGION_COORDS.get(continent, (0.0, 0.0))

            rows.append({
                "id": geo_id,
                "description": info.get("label", region_key),
                "country": info["countries"][0] if len(info.get("countries", [])) == 1 else "",
                "latitude": coords[0] if coords else None,
                "longitude": coords[1] if coords else None,
            })
            result_map[region_key] = geo_id

        if rows:
            stmt = pg_insert(Geography).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "description": stmt.excluded.description,
                    "latitude": stmt.excluded.latitude,
                    "longitude": stmt.excluded.longitude,
                },
            )
            await self.db.execute(stmt)
            await self.db.flush()
            logger.info(f"Created {len(rows)} region geography records")

        return result_map

    # ------------------------------------------------------------------
    # Step 3: Sites with Master Type Inference
    # ------------------------------------------------------------------

    def _infer_sites(self, preview: ConfigPreview) -> List[SitePreview]:
        """Infer sites and their master types from SAP data."""
        t001w = self._data.get("T001W", pd.DataFrame())
        apo_loc = self._data.get("/SAPAPO/LOC", pd.DataFrame())

        # Collect all site keys
        site_keys: Dict[str, str] = {}  # key → name

        site_adrnr: Dict[str, str] = {}  # plant key → ADRNR (address number)
        if not t001w.empty and "WERKS" in t001w.columns:
            for _, row in t001w.iterrows():
                key = str(row["WERKS"]).strip()
                name = str(row.get("NAME1", key)).strip()
                site_keys[key] = name
                adrnr = str(row.get("ADRNR", "")).strip()
                if adrnr and adrnr != "nan":
                    site_adrnr[key] = adrnr

        if not apo_loc.empty and "LOCNO" in apo_loc.columns:
            for _, row in apo_loc.iterrows():
                key = str(row["LOCNO"]).strip()
                if key not in site_keys:
                    name = str(row.get("LOCDESC", key)).strip()
                    site_keys[key] = name

        # Gather inference data
        plants_with_bom = self._get_plants_with_bom()
        vendor_plants = self._get_vendor_plant_codes()
        customer_sites = self._get_customer_ship_to_sites()

        # Product counts per site
        marc = self._data.get("MARC", pd.DataFrame())
        site_product_counts: Dict[str, int] = {}
        if not marc.empty and "WERKS" in marc.columns:
            counts = marc.groupby("WERKS")["MATNR"].nunique()
            site_product_counts = counts.to_dict()

        # Build previews
        site_previews = []
        for key, name in site_keys.items():
            master_type = self._infer_master_type(
                key, plants_with_bom, vendor_plants, customer_sites
            )
            site_previews.append(SitePreview(
                key=key,
                name=name,
                inferred_master_type=master_type,
                product_count=site_product_counts.get(key, 0),
                has_bom=key in plants_with_bom,
                is_vendor_location=key in vendor_plants,
                is_customer_destination=key in customer_sites,
                address_number=site_adrnr.get(key, ""),
            ))

        return site_previews

    def _infer_master_type(
        self,
        site_key: str,
        plants_with_bom: Set[str],
        vendor_plants: Set[str],
        customer_sites: Set[str],
    ) -> str:
        """Infer master type for a site from SAP data patterns."""
        if site_key in plants_with_bom:
            return MASTER_MANUFACTURER

        if site_key in vendor_plants:
            return MASTER_VENDOR

        if site_key in customer_sites:
            return MASTER_CUSTOMER

        return MASTER_INVENTORY

    def _get_plants_with_bom(self) -> Set[str]:
        """Get plant codes that have in-house production.

        Uses MARC.BESKZ='E' (in-house production) as the primary signal,
        with PLPO routing operations as a fallback.
        """
        marc = self._data.get("MARC", pd.DataFrame())
        result: Set[str] = set()

        # Primary: MARC procurement type E = in-house production
        if not marc.empty and "BESKZ" in marc.columns and "WERKS" in marc.columns:
            prod_plants = marc[marc["BESKZ"].astype(str).str.strip() == "E"]["WERKS"].unique()
            result.update(str(p).strip() for p in prod_plants)

        # Fallback: plants referenced in routing operations (PLPO)
        if not result:
            plpo = self._data.get("PLPO", pd.DataFrame())
            if not plpo.empty and "WERKS" in plpo.columns:
                result.update(str(w).strip() for w in plpo["WERKS"].unique())

        return result

    def _get_vendor_plant_codes(self) -> Set[str]:
        """Get site keys that appear as vendor locations in LFA1."""
        lfa1 = self._data.get("LFA1", pd.DataFrame())
        if lfa1.empty:
            return set()
        # Vendor codes are not plant codes, but we track them as external sites
        return set(str(v).strip() for v in lfa1.get("LIFNR", pd.Series()).unique())

    def _get_customer_ship_to_sites(self) -> Set[str]:
        """Get site keys that appear as customer ship-to destinations."""
        kna1 = self._data.get("KNA1", pd.DataFrame())
        if kna1.empty:
            return set()
        return set(str(c).strip() for c in kna1.get("KUNNR", pd.Series()).unique())

    async def _create_sites(self, overrides: Dict[str, str], opts: Optional[Dict[str, Any]] = None) -> int:
        """Create Site entities from inferred data."""
        preview = ConfigPreview()
        site_previews = self._infer_sites(preview)

        # Determine site type definitions from inferred master types
        site_type_defs = [
            {"type": "PLANT", "label": "Plant", "order": 0, "master_type": "MANUFACTURER"},
            {"type": "DC", "label": "Distribution Center", "order": 1, "master_type": "INVENTORY"},
            {"type": "SUPPLIER", "label": "Vendor", "order": 2, "master_type": "VENDOR", "tpartner_type": "vendor", "is_external": True},
            {"type": "CUSTOMER", "label": "Customer", "order": 3, "master_type": "CUSTOMER", "tpartner_type": "customer", "is_external": True},
        ]
        self._config.site_type_definitions = site_type_defs
        await self.db.flush()

        master_to_dag = {
            MASTER_MANUFACTURER: "PLANT",
            MASTER_INVENTORY: "DC",
            MASTER_VENDOR: "SUPPLIER",
            MASTER_CUSTOMER: "CUSTOMER",
            # Legacy values that may exist in old DB rows
            "VENDOR": "SUPPLIER",
            "CUSTOMER": "CUSTOMER",
        }

        count = 0
        for sp in site_previews:
            # Apply user override if provided
            master_type = overrides.get(sp.key, sp.inferred_master_type)
            dag_type = master_to_dag.get(master_type, "DC")

            # Link to geography via SAP ADRNR → config_id + address_number
            geo_id = None
            if sp.address_number:
                geo_id = f"{self._config.id}_{sp.address_number}"

            site = Site(
                config_id=self._config.id,
                name=sp.key,
                type=sp.name,
                dag_type=dag_type,
                master_type=master_type,
                geo_id=geo_id,
                attributes={
                    "sap_plant_code": sp.key,
                    "has_bom": sp.has_bom,
                    "product_count": sp.product_count,
                },
            )
            self.db.add(site)
            await self.db.flush()
            self._sites[sp.key] = site
            count += 1

        # AWS SC Compliance: Vendors and customers are TradingPartner records,
        # NOT proxy Site records. They connect to the DAG via TransportationLane
        # from_partner_id / to_partner_id fields. TradingPartner records are
        # created in _create_partners_and_sourcing() (Step 5), and lanes with
        # partner endpoints are created in _create_lanes() (Step 9).
        #
        # The geo hierarchy handles aggregation/filtering of partners for display.

        # Cache country → region_key lookups for use by _create_lanes
        # (still needed for grouping partners into regional lanes)
        build_opts = opts or {}
        supply_regions, demand_regions = self._compute_market_regions(
            max_supply_regions=build_opts.get("max_supply_regions", 8),
            max_demand_regions=build_opts.get("max_demand_regions", 8),
            promotion_threshold=build_opts.get("region_promotion_threshold", 0.25),
        )
        self._supply_country_region: Dict[str, str] = {}
        for rk, info in supply_regions.items():
            for c in info["countries"]:
                self._supply_country_region[c] = rk
        self._demand_country_region: Dict[str, str] = {}
        for rk, info in demand_regions.items():
            for c in info["countries"]:
                self._demand_country_region[c] = rk

        logger.info(f"Created {count} internal sites (no proxy vendor/customer sites — using TradingPartner endpoints)")
        return count

    async def _create_hierarchy_nodes(self) -> Dict[str, int]:
        """Create SiteHierarchyNode and ProductHierarchyNode from SAP geo and product hierarchy tables.

        Site hierarchy:  Company (T001) → Country (T005T) → Region (T005U) → Plant (T001W)
        Product hierarchy: T179 tree with text from T179T, linked to products via MARA.PRDHA
        """
        tenant_id = self._config.tenant_id
        site_count = 0
        product_count = 0

        # ── SITE GEO HIERARCHY ────────────────────────────────────────────
        t001 = self._data.get("T001", pd.DataFrame())
        t001w = self._data.get("T001W", pd.DataFrame())
        t005t = self._data.get("T005T", pd.DataFrame())
        t005u = self._data.get("T005U", pd.DataFrame())

        # Build country name lookup: LAND1 → English name
        country_names: Dict[str, str] = {}
        if not t005t.empty:
            for _, r in t005t.iterrows():
                country_names[str(r.get("LAND1", "")).strip()] = str(r.get("LANDX", "")).strip()

        # Build region name lookup: (LAND1, BLAND) → English name
        region_names: Dict[Tuple[str, str], str] = {}
        if not t005u.empty:
            for _, r in t005u.iterrows():
                key = (str(r.get("LAND1", "")).strip(), str(r.get("BLAND", "")).strip())
                region_names[key] = str(r.get("BEZEI", "")).strip()

        # Root: Company from T001
        if not t001.empty:
            company_row = t001.iloc[0]
            company_code = str(company_row.get("BUKRS", "")).strip()
            company_name = str(company_row.get("BUTXT", "")).strip() or f"Company {company_code}"
        else:
            company_code = f"TENANT_{tenant_id}"
            company_name = self._config.name or "Company"

        root_code = f"CO_{company_code}"
        root = SiteHierarchyNode(
            tenant_id=tenant_id,
            code=root_code,
            name=company_name,
            hierarchy_level="COMPANY",
            hierarchy_path=root_code,
            depth=0,
        )
        self.db.add(root)
        await self.db.flush()
        site_count += 1

        # Group plants by country → region
        country_nodes: Dict[str, SiteHierarchyNode] = {}
        region_nodes: Dict[Tuple[str, str], SiteHierarchyNode] = {}

        _seen_site_codes: set = set()
        if not t001w.empty:
            for _, plant in t001w.iterrows():
                werks = str(plant.get("WERKS", "")).strip()
                land1 = str(plant.get("LAND1", "")).strip()
                regio = str(plant.get("REGIO", "")).strip()

                # Skip plants not in our config's sites
                if werks not in self._sites:
                    continue

                # Country node (idempotent)
                if land1 and land1 not in country_nodes:
                    cname = country_names.get(land1, land1)
                    ccode = f"COUNTRY_{land1}"
                    cnode = SiteHierarchyNode(
                        tenant_id=tenant_id,
                        code=ccode,
                        name=cname,
                        hierarchy_level="COUNTRY",
                        hierarchy_path=f"{root_code}/{ccode}",
                        depth=1,
                        parent_id=root.id,
                    )
                    self.db.add(cnode)
                    await self.db.flush()
                    country_nodes[land1] = cnode
                    site_count += 1

                # Region/State node (idempotent)
                region_key = (land1, regio)
                if regio and region_key not in region_nodes and land1 in country_nodes:
                    rname = region_names.get(region_key, regio)
                    rcode = f"REGION_{land1}_{regio}"
                    rnode = SiteHierarchyNode(
                        tenant_id=tenant_id,
                        code=rcode,
                        name=rname,
                        hierarchy_level="STATE",
                        hierarchy_path=f"{root_code}/COUNTRY_{land1}/{rcode}",
                        depth=2,
                        parent_id=country_nodes[land1].id,
                    )
                    self.db.add(rnode)
                    await self.db.flush()
                    region_nodes[region_key] = rnode
                    site_count += 1

                # Plant node — link to the Site entity (skip duplicates)
                pcode = f"SITE_{werks}"
                if pcode not in _seen_site_codes:
                    _seen_site_codes.add(pcode)
                    parent_node = region_nodes.get(region_key) or country_nodes.get(land1) or root
                    site_entity = self._sites.get(werks)
                    plant_name = str(plant.get("NAME1", "")).strip() or werks
                    pnode = SiteHierarchyNode(
                        tenant_id=tenant_id,
                        code=pcode,
                        name=plant_name,
                        hierarchy_level="SITE",
                        hierarchy_path=f"{parent_node.hierarchy_path}/{pcode}",
                        depth=parent_node.depth + 1,
                        parent_id=parent_node.id,
                        site_id=site_entity.id if site_entity else None,
                    )
                    self.db.add(pnode)
                    site_count += 1

        await self.db.flush()
        logger.info(f"Created {site_count} site hierarchy nodes (Company→Country→Region→Plant)")

        # ── PRODUCT HIERARCHY ─────────────────────────────────────────────
        _seen_product_codes: set = set()
        t179 = self._data.get("T179", pd.DataFrame())
        t179t = self._data.get("T179T", pd.DataFrame())

        # Build PRODH → text lookup
        prodh_text: Dict[str, str] = {}
        if not t179t.empty:
            for _, r in t179t.iterrows():
                prodh_text[str(r.get("PRODH", "")).strip()] = str(r.get("VTEXT", "")).strip()

        # Check if T179 has usable data (non-empty with PRODH column)
        has_t179 = not t179.empty and "PRODH" in t179.columns

        if has_t179 or self._products:
            # Root node (always created if we have products)
            prod_root_code = f"PRODUCTS_{tenant_id}"
            prod_root = ProductHierarchyNode(
                tenant_id=tenant_id,
                code=prod_root_code,
                name="All Products",
                hierarchy_level="CATEGORY",
                hierarchy_path=prod_root_code,
                depth=0,
            )
            self.db.add(prod_root)
            await self.db.flush()
            product_count += 1

            prodh_nodes: Dict[str, ProductHierarchyNode] = {"": prod_root}

            if has_t179:
                # T179 rows have PRODH (hierarchy code) and STUFE (level: 1, 2, 3)
                # PRODH codes are hierarchical: "00001" (level 1), "0000100001" (level 2),
                # "000010000100000001" (level 3). Parent is determined by prefix.
                level_names = {0: "CATEGORY", 1: "FAMILY", 2: "GROUP", 3: "PRODUCT"}

                # Sort by PRODH length so parents are created before children
                t179_sorted = t179.sort_values(by="PRODH", key=lambda s: s.str.len())

                for _, r in t179_sorted.iterrows():
                    prodh = str(r.get("PRODH", "")).strip()
                    stufe = int(r.get("STUFE", 0)) if pd.notna(r.get("STUFE")) else 0
                    if not prodh or stufe == 0:
                        continue  # root or empty

                    # Find parent by progressively shortening PRODH
                    parent = prod_root
                    for candidate_len in range(len(prodh) - 1, 0, -1):
                        candidate = prodh[:candidate_len]
                        if candidate in prodh_nodes:
                            parent = prodh_nodes[candidate]
                            break

                    text = prodh_text.get(prodh, f"Category {prodh}")
                    hlevel = level_names.get(stufe, "GROUP")
                    hcode = f"PRODH_{prodh}"
                    node = ProductHierarchyNode(
                        tenant_id=tenant_id,
                        code=hcode,
                        name=text,
                        hierarchy_level=hlevel,
                        hierarchy_path=f"{parent.hierarchy_path}/{hcode}",
                        depth=parent.depth + 1,
                        parent_id=parent.id,
                    )
                    self.db.add(node)
                    await self.db.flush()
                    prodh_nodes[prodh] = node
                    product_count += 1

                # Link products to hierarchy nodes via MARA.PRDHA
                mara = self._data.get("MARA", pd.DataFrame())
                if not mara.empty:
                    linked = 0
                    for _, r in mara.iterrows():
                        prdha = str(r.get("PRDHA", "")).strip()
                        matnr = str(r.get("MATNR", "")).strip()
                        if prdha and prdha in prodh_nodes and matnr in self._products:
                            product_entity = self._products[matnr]
                            # Find or create a leaf node for this product
                            parent_h = prodh_nodes[prdha]
                            pcode = f"PROD_{product_entity.id}_{tenant_id}"
                            if pcode in _seen_product_codes:
                                continue
                            _seen_product_codes.add(pcode)
                            leaf = ProductHierarchyNode(
                                tenant_id=tenant_id,
                                code=pcode,
                                name=product_entity.description or matnr,
                                hierarchy_level="PRODUCT",
                                hierarchy_path=f"{parent_h.hierarchy_path}/{pcode}",
                                depth=parent_h.depth + 1,
                                parent_id=parent_h.id,
                                product_id=product_entity.id,
                            )
                            self.db.add(leaf)
                            product_count += 1
                            linked += 1
                    await self.db.flush()
                    logger.info(f"Linked {linked} products to T179 hierarchy nodes")

            else:
                # Fallback: T179 is empty — build hierarchy from MARA.MATKL (material group)
                # and MARA.PRDHA (product hierarchy code, may also be empty)
                logger.info("T179 is empty — building product hierarchy from MARA.MATKL (material group)")
                mara = self._data.get("MARA", pd.DataFrame())
                matkl_nodes: Dict[str, ProductHierarchyNode] = {}

                # First pass: collect unique MATKL groups and PRDHA level-1 codes
                prdha_level1: Dict[str, str] = {}
                if not mara.empty and "PRDHA" in mara.columns:
                    for _, r in mara.iterrows():
                        prdha = str(r.get("PRDHA", "")).strip()
                        matkl = str(r.get("MATKL", "")).strip()
                        if prdha and len(prdha) >= 5:
                            # Level 1 is typically first 5 chars of PRDHA
                            l1 = prdha[:5]
                            if l1 not in prdha_level1:
                                prdha_level1[l1] = prodh_text.get(l1, f"Category {l1}")

                # Use PRDHA level-1 if available, otherwise fall back to MATKL
                use_prdha = len(prdha_level1) > 0

                if use_prdha:
                    # Create group nodes from PRDHA level-1 codes
                    for l1_code, l1_name in sorted(prdha_level1.items()):
                        gcode = f"PRODH_{l1_code}"
                        gnode = ProductHierarchyNode(
                            tenant_id=tenant_id,
                            code=gcode,
                            name=l1_name,
                            hierarchy_level="FAMILY",
                            hierarchy_path=f"{prod_root_code}/{gcode}",
                            depth=1,
                            parent_id=prod_root.id,
                        )
                        self.db.add(gnode)
                        await self.db.flush()
                        prodh_nodes[l1_code] = gnode
                        product_count += 1

                # Create MATKL group nodes for products not covered by PRDHA
                if not mara.empty and "MATKL" in mara.columns:
                    for _, r in mara.iterrows():
                        matkl = str(r.get("MATKL", "")).strip()
                        if not matkl:
                            matkl = "UNCATEGORIZED"
                        if matkl not in matkl_nodes:
                            gcode = f"MATKL_{matkl}"
                            gnode = ProductHierarchyNode(
                                tenant_id=tenant_id,
                                code=gcode,
                                name=f"Material Group {matkl}",
                                hierarchy_level="GROUP",
                                hierarchy_path=f"{prod_root_code}/{gcode}",
                                depth=1,
                                parent_id=prod_root.id,
                            )
                            self.db.add(gnode)
                            await self.db.flush()
                            matkl_nodes[matkl] = gnode
                            product_count += 1

                # Link products to PRDHA or MATKL nodes
                linked = 0
                if not mara.empty:
                    for _, r in mara.iterrows():
                        matnr = str(r.get("MATNR", "")).strip()
                        if matnr not in self._products:
                            continue
                        product_entity = self._products[matnr]

                        # Try PRDHA first (level-1 prefix match)
                        parent_h = None
                        prdha = str(r.get("PRDHA", "")).strip() if "PRDHA" in r.index else ""
                        if prdha and len(prdha) >= 5:
                            l1 = prdha[:5]
                            parent_h = prodh_nodes.get(l1)

                        # Fall back to MATKL
                        if parent_h is None:
                            matkl = str(r.get("MATKL", "")).strip() if "MATKL" in r.index else ""
                            if not matkl:
                                matkl = "UNCATEGORIZED"
                            parent_h = matkl_nodes.get(matkl, prod_root)

                        pcode = f"PROD_{product_entity.id}_{tenant_id}"
                        leaf = ProductHierarchyNode(
                            tenant_id=tenant_id,
                            code=pcode,
                            name=product_entity.description or matnr,
                            hierarchy_level="PRODUCT",
                            hierarchy_path=f"{parent_h.hierarchy_path}/{pcode}",
                            depth=parent_h.depth + 1,
                            parent_id=parent_h.id,
                            product_id=product_entity.id,
                        )
                        self.db.add(leaf)
                        product_count += 1
                        linked += 1
                    await self.db.flush()
                    logger.info(f"Linked {linked} products to MATKL/PRDHA hierarchy nodes (T179 fallback)")

        logger.info(f"Created {product_count} product hierarchy nodes total")
        return {"site_nodes": site_count, "product_nodes": product_count}

    def _compute_market_regions(
        self,
        max_supply_regions: int = 8,
        max_demand_regions: int = 8,
        promotion_threshold: float = 0.25,
    ) -> Tuple[Dict[str, dict], Dict[str, dict]]:
        """Compute supply and demand regions from vendor/customer country data.

        Uses UN M49 continent mapping from bundled JSON.  High-volume countries
        that exceed *promotion_threshold* of their continent's partner count
        are promoted to their own region site (e.g. "Americas" splits into
        "United States" + "Americas" when US has >25 % of the continent's vendors).

        Args:
            max_supply_regions: Cap on the number of supply region sites created.
            max_demand_regions: Cap on the number of demand region sites created.
            promotion_threshold: Fraction (0-1) of a continent's partners a
                single country must exceed to be promoted to its own region.

        Returns:
            (supply_regions, demand_regions) — each is a dict of
            region_key → {label, countries, count}.
        """
        lfa1 = self._data.get("LFA1", pd.DataFrame())
        kna1 = self._data.get("KNA1", pd.DataFrame())

        def _build_regions(
            df: pd.DataFrame, country_col: str, role: str, max_regions: int,
        ) -> Dict[str, dict]:
            if df.empty or country_col not in df.columns:
                return {}

            # Count partners per country
            country_counts: Counter = Counter()
            for _, row in df.iterrows():
                country = str(row.get(country_col, "")).strip().upper()
                if country:
                    country_counts[country] += 1

            # Group countries by continent
            continent_countries: Dict[str, Counter] = {}
            for country, cnt in country_counts.items():
                continent = _COUNTRY_TO_CONTINENT.get(country, "Other")
                continent_countries.setdefault(continent, Counter())[country] = cnt

            # Build regions — promote high-volume countries within their continent
            regions: Dict[str, Dict[str, Any]] = {}
            for continent, c_counts in continent_countries.items():
                total = sum(c_counts.values())
                promoted: Set[str] = set()
                for country, cnt in c_counts.most_common():
                    if cnt / total >= promotion_threshold and cnt >= 5:
                        promoted.add(country)

                # Create promoted country regions
                for country in promoted:
                    rk = country  # region key = ISO code
                    regions[rk] = {
                        "label": f"{country} {role}",
                        "countries": [country],
                        "count": c_counts[country],
                        "continent": continent,
                    }

                # Remaining countries stay in the continent region
                remaining = {c: n for c, n in c_counts.items() if c not in promoted}
                if remaining:
                    rk = continent.upper().replace(" ", "_")
                    if rk in regions:
                        # Merge into existing continent region
                        regions[rk]["countries"].extend(sorted(remaining.keys()))
                        regions[rk]["count"] += sum(remaining.values())
                    else:
                        regions[rk] = {
                            "label": f"{continent} {role}",
                            "countries": sorted(remaining.keys()),
                            "count": sum(remaining.values()),
                            "continent": continent,
                        }

            # If we exceed max_regions, merge smallest regions into their
            # continent peers until under the limit.
            while len(regions) > max_regions:
                # Find the smallest region
                smallest_key = min(regions, key=lambda k: regions[k]["count"])
                smallest = regions.pop(smallest_key)
                continent = smallest.get("continent", "Other")
                continent_key = continent.upper().replace(" ", "_")

                # Try merging into continent peer; if none, merge into largest
                if continent_key in regions:
                    target_key = continent_key
                else:
                    target_key = max(regions, key=lambda k: regions[k]["count"])

                regions[target_key]["countries"] = sorted(
                    set(regions[target_key]["countries"]) | set(smallest["countries"])
                )
                regions[target_key]["count"] += smallest["count"]

            # Sort countries lists
            for info in regions.values():
                info["countries"] = sorted(info["countries"])

            return regions

        supply_regions = _build_regions(lfa1, "LAND1", "Suppliers", max_supply_regions)
        demand_regions = _build_regions(kna1, "LAND1", "Customers", max_demand_regions)
        return supply_regions, demand_regions

    # ------------------------------------------------------------------
    # Step 4: Products
    # ------------------------------------------------------------------

    async def _create_products(self) -> int:
        """Create Product entities from MARA/MARC/MAKT."""
        mara = self._data.get("MARA", pd.DataFrame())
        marc = self._data.get("MARC", pd.DataFrame())
        mvke = self._data.get("MVKE", pd.DataFrame())
        makt = self._data.get("MAKT", pd.DataFrame())

        if mara.empty and marc.empty:
            logger.warning("No material data found")
            return 0

        # Merge MAKT descriptions into MARA (MAKT has MATNR + SPRAS + MAKTX)
        if not mara.empty and not makt.empty and "MATNR" in makt.columns and "MAKTX" in makt.columns:
            # Filter to English descriptions only (SPRAS = 'E'), fall back to first available
            if "SPRAS" in makt.columns:
                makt_en = makt[makt["SPRAS"] == "E"].drop_duplicates(subset=["MATNR"])
                if makt_en.empty:
                    makt_en = makt.drop_duplicates(subset=["MATNR"])
            else:
                makt_en = makt.drop_duplicates(subset=["MATNR"])
            mara = mara.merge(
                makt_en[["MATNR", "MAKTX"]],
                on="MATNR",
                how="left",
                suffixes=("", "_makt"),
            )
            logger.info("Merged %d MAKT descriptions into MARA", makt_en.shape[0])

        # Exclude non-physical material types — services, packaging, pipeline,
        # returnable materials, etc. These don't belong in the SC planning network.
        _EXCLUDE_MTART = {"SERV", "DIEN", "NLAG", "VERP", "LEIH", "PIPE", "VEHI", "SWNV", "UNSF", "UNFR"}

        # Get unique physical materials
        materials: Dict[str, Dict[str, Any]] = {}
        skipped_types: Dict[str, int] = {}
        if not mara.empty and "MATNR" in mara.columns:
            for _, row in mara.iterrows():
                key = str(row["MATNR"]).strip()
                mtart = str(row.get("MTART", "")).strip().upper()
                if mtart in _EXCLUDE_MTART:
                    skipped_types[mtart] = skipped_types.get(mtart, 0) + 1
                    continue
                materials[key] = {
                    "name": str(row.get("MAKTX", key)).strip(),
                    "group": str(row.get("MATKL", "")).strip(),
                    "uom": str(row.get("MEINS", "EA")).strip(),
                    "type": mtart,
                }
        if skipped_types:
            logger.info("Excluded %d non-physical materials: %s",
                        sum(skipped_types.values()), skipped_types)

        # Enrich with MVKE product hierarchy
        if not mvke.empty and "MATNR" in mvke.columns and "PRODH" in mvke.columns:
            for _, row in mvke.iterrows():
                key = str(row["MATNR"]).strip()
                if key in materials:
                    materials[key]["hierarchy"] = str(row.get("PRODH", "")).strip()

        prefix = f"CFG{self._config.id}_"
        count = 0
        for mat_key, info in materials.items():
            product_id = f"{prefix}{mat_key}"
            product = Product(
                id=product_id,
                description=info.get("name", mat_key),
                config_id=self._config.id,
                is_active="true",
                category=info.get("group", ""),
                product_group_name=info.get("group", ""),  # maps to DB column "product_group"
                base_uom=info.get("uom", "EA"),
                product_type=info.get("type", ""),
            )
            self.db.add(product)
            self._products[mat_key] = product
            count += 1

        await self.db.flush()
        logger.info(f"Created {count} products")
        return count

    # ------------------------------------------------------------------
    # Step 5: Transportation Lanes (Priority Cascade)
    # ------------------------------------------------------------------

    def _infer_lanes(self, preview: ConfigPreview) -> List[LanePreview]:
        """Infer transportation lanes using priority cascade."""
        lanes: Dict[Tuple[str, str], LanePreview] = {}

        # Source 1: APO TRLANE (explicit — best quality)
        trlane = self._data.get("/SAPAPO/TRLANE", pd.DataFrame())
        if not trlane.empty and "LOCFR" in trlane.columns:
            for _, row in trlane.iterrows():
                src = str(row["LOCFR"]).strip()
                dst = str(row["LOCTO"]).strip()
                key = (src, dst)
                if key not in lanes:
                    lanes[key] = LanePreview(
                        from_key=src, to_key=dst,
                        source="apo_trlane",
                        lead_time_days=int(pd.to_numeric(row.get("TRANSTIME", 0), errors="coerce") or 0),
                    )
        else:
            preview.warnings.append("No APO TRLANE data — lanes inferred from source list + PO history")

        # Source 2: EORD source list (vendor → plant)
        eord = self._data.get("EORD", pd.DataFrame())
        if not eord.empty and "LIFNR" in eord.columns:
            for _, row in eord.iterrows():
                src = str(row["LIFNR"]).strip()
                dst = str(row["WERKS"]).strip()
                key = (src, dst)
                if key not in lanes:
                    lanes[key] = LanePreview(
                        from_key=src, to_key=dst,
                        source="eord",
                    )

        # Source 3: Historical EKPO (vendor-plant PO patterns)
        ekpo = self._data.get("EKPO", pd.DataFrame())
        ekko = self._data.get("EKKO", pd.DataFrame())
        if not ekpo.empty and not ekko.empty:
            merged = ekpo.merge(
                ekko[["EBELN", "LIFNR"]].drop_duplicates(),
                on="EBELN", how="left",
            )
            if "LIFNR" in merged.columns and "WERKS" in merged.columns:
                po_flows = merged.groupby(["LIFNR", "WERKS"]).size()
                for (vendor, plant), count in po_flows.items():
                    if count >= 3:  # threshold
                        key = (str(vendor).strip(), str(plant).strip())
                        if key not in lanes:
                            lanes[key] = LanePreview(
                                from_key=key[0], to_key=key[1],
                                source="ekpo_history",
                                product_count=count,
                            )

        # Source 4: Historical deliveries (plant → customer)
        likp = self._data.get("LIKP", pd.DataFrame())
        lips = self._data.get("LIPS", pd.DataFrame())
        if not likp.empty and not lips.empty:
            if "KUNNR" in likp.columns and "WERKS" in lips.columns:
                merged_del = lips.merge(
                    likp[["VBELN", "KUNNR"]].drop_duplicates(),
                    on="VBELN", how="left",
                )
                if "KUNNR" in merged_del.columns:
                    del_flows = merged_del.groupby(["WERKS", "KUNNR"]).size()
                    for (plant, customer), count in del_flows.items():
                        if count >= 3:
                            key = (str(plant).strip(), str(customer).strip())
                            if key not in lanes:
                                lanes[key] = LanePreview(
                                    from_key=key[0], to_key=key[1],
                                    source="delivery_history",
                                    product_count=count,
                                )

        return list(lanes.values())

    async def _create_lanes(self) -> int:
        """Create TransportationLane entities connecting regional market sites to plants.

        Lane topology:
        - SUPPLY_{region} → {plant}  (inbound: regional vendors supply to plant)
        - {plant} → DEMAND_{region}  (outbound: plant ships to regional customers)
        - {plant_A} → {plant_B}      (inter-plant transfers, if detected)

        Lanes are only created where actual sourcing/shipping relationships exist
        in the SAP data (EORD/EKPO for inbound, LIKP/LIPS/VBAP for outbound).
        """
        lfa1 = self._data.get("LFA1", pd.DataFrame())
        kna1 = self._data.get("KNA1", pd.DataFrame())

        # Build vendor → region lookup using cached country→region mapping
        supply_cr = getattr(self, "_supply_country_region", {})
        demand_cr = getattr(self, "_demand_country_region", {})

        vendor_region: Dict[str, str] = {}
        if not lfa1.empty and "LIFNR" in lfa1.columns and "LAND1" in lfa1.columns:
            for _, row in lfa1.iterrows():
                vid = str(row["LIFNR"]).strip()
                country = str(row.get("LAND1", "")).strip().upper()
                vendor_region[vid] = supply_cr.get(country, _COUNTRY_TO_CONTINENT.get(country, "OTHER").upper().replace(" ", "_"))

        # Build customer → region lookup
        customer_region: Dict[str, str] = {}
        if not kna1.empty and "KUNNR" in kna1.columns and "LAND1" in kna1.columns:
            for _, row in kna1.iterrows():
                cid = str(row["KUNNR"]).strip()
                country = str(row.get("LAND1", "")).strip().upper()
                customer_region[cid] = demand_cr.get(country, _COUNTRY_TO_CONTINENT.get(country, "OTHER").upper().replace(" ", "_"))

        # Compute average vendor lead time per region from EINE
        eine = self._data.get("EINE", pd.DataFrame())
        region_lead_times: Dict[str, List[float]] = {}
        if not eine.empty and "PLIFZ" in eine.columns and "LIFNR" in eine.columns:
            for _, row in eine.iterrows():
                vid = str(row.get("LIFNR", "")).strip()
                lt_raw = pd.to_numeric(row.get("PLIFZ", 0), errors="coerce")
                region = vendor_region.get(vid, "OTHER")
                if lt_raw and lt_raw > 0:
                    region_lead_times.setdefault(region, []).append(float(lt_raw))
        avg_region_lt: Dict[str, int] = {}
        for rk, lts in region_lead_times.items():
            avg_region_lt[rk] = max(1, int(sum(lts) / len(lts)))

        count = 0
        # Track created lanes to avoid duplicates.
        # Keys: (from_partner_id|None, from_site_id|None, to_site_id|None, to_partner_id|None)
        created_lanes: Set[Tuple] = set()

        # ── Inbound lanes: TradingPartner (vendor) → Site (plant) ──────────
        # Determine which individual vendors actually source to which plants.
        eord = self._data.get("EORD", pd.DataFrame())
        ekpo = self._data.get("EKPO", pd.DataFrame())
        ekko = self._data.get("EKKO", pd.DataFrame())

        # plant_key → set of vendor_id strings
        plant_vendors: Dict[str, Set[str]] = {}
        if not eord.empty and "LIFNR" in eord.columns and "WERKS" in eord.columns:
            for _, row in eord.iterrows():
                vid = str(row["LIFNR"]).strip()
                plant = str(row["WERKS"]).strip()
                if vid in self._partner_ids and plant in self._sites:
                    plant_vendors.setdefault(plant, set()).add(vid)
        if not ekpo.empty and not ekko.empty:
            merged = ekpo.merge(
                ekko[["EBELN", "LIFNR"]].drop_duplicates(), on="EBELN", how="left",
            )
            if "LIFNR" in merged.columns and "WERKS" in merged.columns:
                for _, row in merged.iterrows():
                    vid = str(row["LIFNR"]).strip()
                    plant = str(row["WERKS"]).strip()
                    if vid in self._partner_ids and plant in self._sites:
                        plant_vendors.setdefault(plant, set()).add(vid)

        # Create one inbound lane per active vendor→plant relationship
        for plant_key, vendors in plant_vendors.items():
            plant_site = self._sites.get(plant_key)
            if not plant_site:
                continue
            for vid in vendors:
                partner_id = self._partner_ids.get(vid)
                if not partner_id:
                    continue
                lane_key = (partner_id, None, plant_site.id, None)
                if lane_key not in created_lanes:
                    region = vendor_region.get(vid, "OTHER")
                    lt = avg_region_lt.get(region, 7)
                    lane = TransportationLane(
                        config_id=self._config.id,
                        from_partner_id=partner_id,
                        to_site_id=plant_site.id,
                        capacity=10000,
                        lead_time_days={"min": max(1, lt - 2), "max": lt + 2},
                        supply_lead_time={"type": "deterministic", "value": lt},
                        demand_lead_time={"type": "deterministic", "value": 1},
                    )
                    self.db.add(lane)
                    created_lanes.add(lane_key)
                    count += 1

        # ── Outbound lanes: Site (plant) → TradingPartner (customer) ───────
        # Determine which customers each plant ships to (from deliveries/orders).
        likp = self._data.get("LIKP", pd.DataFrame())
        lips = self._data.get("LIPS", pd.DataFrame())
        vbap = self._data.get("VBAP", pd.DataFrame())

        plant_customers: Dict[str, Set[str]] = {}
        if not lips.empty and not likp.empty:
            if "KUNNR" in likp.columns and "WERKS" in lips.columns:
                merged_del = lips.merge(
                    likp[["VBELN", "KUNNR"]].drop_duplicates(), on="VBELN", how="left",
                )
                if "KUNNR" in merged_del.columns:
                    for _, row in merged_del.iterrows():
                        cid = str(row["KUNNR"]).strip()
                        plant = str(row["WERKS"]).strip()
                        if cid in self._partner_ids and plant in self._sites:
                            plant_customers.setdefault(plant, set()).add(cid)
        if not vbap.empty and "WERKS" in vbap.columns:
            vbak = self._data.get("VBAK", pd.DataFrame())
            if not vbak.empty and "KUNNR" in vbak.columns:
                merged_so = vbap.merge(
                    vbak[["VBELN", "KUNNR"]].drop_duplicates(), on="VBELN", how="left",
                )
                if "KUNNR" in merged_so.columns:
                    for _, row in merged_so.iterrows():
                        cid = str(row["KUNNR"]).strip()
                        plant = str(row["WERKS"]).strip()
                        if cid in self._partner_ids and plant in self._sites:
                            plant_customers.setdefault(plant, set()).add(cid)

        # Create one outbound lane per active plant→customer relationship.
        # Cap at 50 customers per plant (top by frequency) to keep DAG readable.
        MAX_CUSTOMERS_PER_PLANT = 50
        for plant_key, customers in plant_customers.items():
            plant_site = self._sites.get(plant_key)
            if not plant_site:
                continue
            cust_list = list(customers)[:MAX_CUSTOMERS_PER_PLANT]
            for cid in cust_list:
                partner_id = self._partner_ids.get(cid)
                if not partner_id:
                    continue
                lane_key = (None, plant_site.id, None, partner_id)
                if lane_key not in created_lanes:
                    lane = TransportationLane(
                        config_id=self._config.id,
                        from_site_id=plant_site.id,
                        to_partner_id=partner_id,
                        capacity=10000,
                        lead_time_days={"min": 1, "max": 5},
                        supply_lead_time={"type": "deterministic", "value": 2},
                        demand_lead_time={"type": "deterministic", "value": 1},
                    )
                    self.db.add(lane)
                    created_lanes.add(lane_key)
                    count += 1

        # ── Inter-plant transfers: Site → Site ─────────────────────────────
        eord = self._data.get("EORD", pd.DataFrame())
        if not eord.empty and "FLIFN" in eord.columns:
            inter_plant = eord[eord["FLIFN"].astype(str).str.strip() == "X"]
            if not inter_plant.empty and "LIFNR" in inter_plant.columns and "WERKS" in inter_plant.columns:
                for _, row in inter_plant.iterrows():
                    src = str(row["LIFNR"]).strip()
                    dst = str(row["WERKS"]).strip()
                    if src in self._sites and dst in self._sites:
                        src_site = self._sites[src]
                        dst_site = self._sites[dst]
                        lane_key = (None, src_site.id, dst_site.id, None)
                        if lane_key not in created_lanes:
                            lane = TransportationLane(
                                config_id=self._config.id,
                                from_site_id=src_site.id,
                                to_site_id=dst_site.id,
                                capacity=10000,
                                lead_time_days={"min": 1, "max": 3},
                                supply_lead_time={"type": "deterministic", "value": 2},
                                demand_lead_time={"type": "deterministic", "value": 1},
                            )
                            self.db.add(lane)
                            created_lanes.add(lane_key)
                            count += 1

        # ── Fallback: ensure ALL vendors and customers have at least one lane ─
        # The EORD/EKPO/LIKP/VBAP merge may miss partners if the staging data
        # is incomplete. Create a lane for every trading partner that doesn't
        # already have one, connecting to the first plant.
        plant_sites = {k: v for k, v in self._sites.items()
                       if hasattr(v, 'master_type') and v.master_type in ('MANUFACTURER', 'INVENTORY')}
        # Ensure EVERY trading partner has at least one lane. A vendor without
        # a lane today may get a PO tomorrow. A customer without a lane today
        # may place an order tomorrow. The network must be fully connected.
        if plant_sites and self._partner_ids:
            first_plant = next(iter(plant_sites.values()))
            fallback_count = 0
            # Build set of partners that already have lanes
            partners_with_vendor_lane = {k[0] for k in created_lanes if k[0] is not None}
            partners_with_customer_lane = {k[3] for k in created_lanes if k[3] is not None}

            # Batch-query all partner types to avoid N+1
            from sqlalchemy import select as _s2
            partner_types: Dict[int, str] = {}
            all_pids = list(self._partner_ids.values())
            for i in range(0, len(all_pids), 500):
                batch = all_pids[i:i+500]
                try:
                    rows = await self.db.execute(
                        _s2(TradingPartner._id, TradingPartner.tpartner_type).where(
                            TradingPartner._id.in_(batch)
                        )
                    )
                    for _pid, _tp in rows.fetchall():
                        partner_types[_pid] = _tp
                except Exception:
                    pass

            for biz_key, pid in self._partner_ids.items():
                tp_type = partner_types.get(pid)
                if tp_type == "vendor" and pid not in partners_with_vendor_lane:
                    lane_key = (pid, None, first_plant.id, None)
                    if lane_key not in created_lanes:
                        lane = TransportationLane(
                            config_id=self._config.id,
                            from_partner_id=pid,
                            to_site_id=first_plant.id,
                            capacity=10000,
                            lead_time_days={"min": 3, "max": 10},
                            supply_lead_time={"type": "deterministic", "value": 7},
                            demand_lead_time={"type": "deterministic", "value": 1},
                        )
                        self.db.add(lane)
                        created_lanes.add(lane_key)
                        count += 1
                        fallback_count += 1
                elif tp_type == "customer" and pid not in partners_with_customer_lane:
                    lane_key = (None, first_plant.id, None, pid)
                    if lane_key not in created_lanes:
                        lane = TransportationLane(
                            config_id=self._config.id,
                            from_site_id=first_plant.id,
                            to_partner_id=pid,
                            capacity=10000,
                            lead_time_days={"min": 1, "max": 5},
                            supply_lead_time={"type": "deterministic", "value": 2},
                            demand_lead_time={"type": "deterministic", "value": 1},
                        )
                        self.db.add(lane)
                        created_lanes.add(lane_key)
                        count += 1
                        fallback_count += 1
            if fallback_count:
                logger.info(f"Connected {fallback_count} additional partners to network (every partner must have a lane)")

        # Legacy fallback for empty configs (kept for backward compatibility)
        if plant_sites and count == 0 and self._partner_ids:
            first_plant = next(iter(plant_sites.values()))
            # Pick first 10 vendors as fallback
            for vid, pid in list(self._partner_ids.items())[:10]:
                if vid in self._trading_partners and self._trading_partners[vid] == vid:
                    # It's a vendor (stored by LIFNR key)
                    lane_key = (pid, None, first_plant.id, None)
                    if lane_key not in created_lanes:
                        lane = TransportationLane(
                            config_id=self._config.id,
                            from_partner_id=pid,
                            to_site_id=first_plant.id,
                            capacity=10000,
                            lead_time_days={"min": 3, "max": 10},
                            supply_lead_time={"type": "deterministic", "value": 7},
                            demand_lead_time={"type": "deterministic", "value": 1},
                        )
                        self.db.add(lane)
                        created_lanes.add(lane_key)
                        count += 1
            logger.info(f"Fallback: created {count} default vendor lanes")

        await self.db.flush()
        vendor_lanes = sum(1 for k in created_lanes if k[0] is not None)
        customer_lanes = sum(1 for k in created_lanes if k[3] is not None)
        transfer_lanes = sum(1 for k in created_lanes if k[0] is None and k[3] is None)
        logger.info(
            f"Created {count} transportation lanes "
            f"({vendor_lanes} vendor→plant, {customer_lanes} plant→customer, {transfer_lanes} inter-site)"
        )
        return count

    # ------------------------------------------------------------------
    # Step 6: Trading Partners & Sourcing
    # ------------------------------------------------------------------

    async def _create_partners_and_sourcing(self) -> Tuple[int, int, int]:
        """Create TradingPartner, VendorProduct, SourcingRules."""
        vendor_count = 0
        customer_count = 0
        sourcing_count = 0

        # Vendors from LFA1 (deduplicate by LIFNR)
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        # Build country → geo_id lookup from existing Geography records
        geo_lookup: Dict[str, int] = {}
        try:
            from app.models.sc_entities import Geography
            from sqlalchemy import select as _sel
            geo_rows = await self.db.execute(_sel(Geography.id, Geography.geo_id))
            for gid, geo_code in geo_rows.fetchall():
                if geo_code:
                    geo_lookup[str(geo_code).strip().upper()] = gid
        except Exception:
            pass

        lfa1 = self._data.get("LFA1", pd.DataFrame())
        if not lfa1.empty and "LIFNR" in lfa1.columns:
            seen_vendors: Dict[str, dict] = {}
            for _, row in lfa1.iterrows():
                vendor_id = str(row["LIFNR"]).strip()
                if vendor_id and vendor_id not in seen_vendors:
                    country = str(row.get("LAND1", "")).strip().upper()
                    seen_vendors[vendor_id] = {
                        "id": vendor_id,
                        "tpartner_type": "vendor",
                        "description": str(row.get("NAME1", vendor_id)).strip(),
                        "country": country or None,
                        "city": str(row.get("ORT01", "")).strip() or None,
                        "state_prov": str(row.get("REGIO", "")).strip() or None,
                        "postal_code": str(row.get("PSTLZ", "")).strip() or None,
                        "source": "SAP_LFA1",
                    }
            if seen_vendors:
                vendor_rows = list(seen_vendors.values())
                for i in range(0, len(vendor_rows), 500):
                    batch = vendor_rows[i : i + 500]
                    stmt = pg_insert(TradingPartner).values(batch)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["id"],
                        set_={
                            "description": stmt.excluded.description,
                            "country": stmt.excluded.country,
                            "city": stmt.excluded.city,
                            "state_prov": stmt.excluded.state_prov,
                            "postal_code": stmt.excluded.postal_code,
                            "source": stmt.excluded.source,
                        },
                    )
                    await self.db.execute(stmt)
                for vid in seen_vendors:
                    self._trading_partners[vid] = vid  # store key for reference
                vendor_count = len(seen_vendors)

        # Customers from KNA1 (deduplicate by KUNNR)
        kna1 = self._data.get("KNA1", pd.DataFrame())
        if not kna1.empty and "KUNNR" in kna1.columns:
            seen_customers: Dict[str, dict] = {}
            for _, row in kna1.iterrows():
                customer_id = str(row["KUNNR"]).strip()
                if customer_id and customer_id not in seen_customers:
                    country = str(row.get("LAND1", "")).strip().upper()
                    seen_customers[customer_id] = {
                        "id": customer_id,
                        "tpartner_type": "customer",
                        "description": str(row.get("NAME1", customer_id)).strip(),
                        "country": country or None,
                        "city": str(row.get("ORT01", "")).strip() or None,
                        "state_prov": str(row.get("REGIO", "")).strip() or None,
                        "postal_code": str(row.get("PSTLZ", "")).strip() or None,
                        "source": "SAP_KNA1",
                    }
            if seen_customers:
                customer_rows = list(seen_customers.values())
                for i in range(0, len(customer_rows), 500):
                    batch = customer_rows[i : i + 500]
                    stmt = pg_insert(TradingPartner).values(batch)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["id"],
                        set_={
                            "description": stmt.excluded.description,
                            "country": stmt.excluded.country,
                            "city": stmt.excluded.city,
                            "state_prov": stmt.excluded.state_prov,
                            "postal_code": stmt.excluded.postal_code,
                            "source": stmt.excluded.source,
                        },
                    )
                    await self.db.execute(stmt)
                for cid in seen_customers:
                    self._trading_partners[cid] = cid
                customer_count = len(seen_customers)

        await self.db.flush()

        # Query back _id integers for all upserted TradingPartner records so
        # that _create_lanes() can populate from_partner_id / to_partner_id FKs.
        all_partner_keys = list(self._trading_partners.keys())
        if all_partner_keys:
            from sqlalchemy import select as sa_select
            for i in range(0, len(all_partner_keys), 500):
                batch_keys = all_partner_keys[i : i + 500]
                result = await self.db.execute(
                    sa_select(TradingPartner.id, TradingPartner._id).where(
                        TradingPartner.id.in_(batch_keys)
                    )
                )
                for biz_key, int_id in result.fetchall():
                    self._partner_ids[biz_key] = int_id
            logger.info("Resolved %d TradingPartner _id values for lane creation", len(self._partner_ids))

        # VendorProduct from EINA/EINE (deduplicate by vendor+product)
        eina = self._data.get("EINA", pd.DataFrame())
        eine = self._data.get("EINE", pd.DataFrame())
        if not eina.empty:
            vp_df = self.mapper.map_vendor_products(eina, eine)
            prefix = f"CFG{self._config.id}_"
            seen_vp: set = set()
            for _, row in vp_df.iterrows():
                product_id = f"{prefix}{row['product_id']}"
                vendor_key = str(row["vendor_id"]).strip()
                dedup_key = (vendor_key, product_id)
                if row["product_id"] in self._products and dedup_key not in seen_vp:
                    seen_vp.add(dedup_key)
                    vp = VendorProduct(
                        tpartner_id=vendor_key,
                        product_id=product_id,
                        vendor_unit_cost=float(row.get("net_price", 0) or 0),
                        minimum_order_quantity=float(row.get("min_order_qty", 0) or 0),
                        source="SAP_EINA",
                    )
                    self.db.add(vp)

        # VendorLeadTime from EINE + EORD
        eord = self._data.get("EORD", pd.DataFrame())
        if not eina.empty:
            vlt_df = self.mapper.map_vendor_lead_times(eina, eine, eord)
            seen_vlt: set = set()
            for _, row in vlt_df.iterrows():
                if row["product_id"] in self._products and row.get("site_id") in self._sites:
                    prefix = f"CFG{self._config.id}_"
                    vendor_key = str(row["vendor_id"]).strip()
                    site_id = self._sites[row["site_id"]].id
                    dedup_key = (vendor_key, row["product_id"], site_id)
                    if dedup_key not in seen_vlt:
                        seen_vlt.add(dedup_key)
                        vlt = VendorLeadTime(
                            tpartner_id=vendor_key,
                            product_id=f"{prefix}{row['product_id']}",
                            site_id=site_id,
                            lead_time_days=float(row.get("lead_time_days", 0) or 0),
                            source="SAP_EINE",
                        )
                        self.db.add(vlt)

        # SourcingRules from EORD
        if not eord.empty:
            sr_df = self.mapper.map_sourcing_rules(eord)
            for idx, row in sr_df.iterrows():
                if row["product_id"] in self._products and row["site_id"] in self._sites:
                    prefix = f"CFG{self._config.id}_"
                    product_id = f"{prefix}{row['product_id']}"
                    to_site_id = self._sites[row["site_id"]].id
                    sr = SourcingRules(
                        id=f"{prefix}SR_{sourcing_count}",
                        config_id=self._config.id,
                        product_id=product_id,
                        to_site_id=to_site_id,
                        sourcing_rule_type=row.get("source_type", "buy"),
                        tpartner_id=str(row.get("source_id", "")).strip(),
                        sourcing_priority=int(row.get("priority", 1)),
                        is_active="true",
                        source="SAP_EORD",
                    )
                    self.db.add(sr)
                    sourcing_count += 1

        await self.db.flush()
        logger.info(f"Created {vendor_count} vendors, {customer_count} customers, {sourcing_count} sourcing rules")
        return vendor_count, customer_count, sourcing_count

    # ------------------------------------------------------------------
    # Step 7: BOM & Manufacturing
    # ------------------------------------------------------------------

    async def _create_bom_and_manufacturing(self) -> int:
        """Create ProductBom and ProductionProcess entities.

        BOM resolution requires MAST (material→BOM assignment) to map
        STLNR (BOM number) back to the parent material. Without MAST,
        STPO only has the component material (IDNRK), not the parent.
        """
        bom_count = 0
        prefix = f"CFG{self._config.id}_"

        # BOM from STPO (items) + STKO (headers) + MAST (parent assignment)
        stpo = self._data.get("STPO", pd.DataFrame())
        stko = self._data.get("STKO", pd.DataFrame())
        mast = self._data.get("MAST", pd.DataFrame())

        # Normalize STLNR to zero-padded 8-char string across all BOM tables
        def _norm_stlnr(val) -> str:
            """Normalize STLNR: '27.0' → '00000027', '00000027' → '00000027'."""
            s = str(val).strip()
            # Handle float representation from pandas (e.g., '27.0')
            try:
                n = int(float(s))
                return f"{n:08d}"
            except (ValueError, OverflowError):
                return s

        if not stpo.empty and "STLNR" in stpo.columns:
            # Build STLNR → parent material lookup
            # Priority: MAST table (explicit assignment) > STKO.MATNR (OData extraction)
            bom_parent_map: dict = {}  # STLNR → MATNR (parent material)
            if not mast.empty and "STLNR" in mast.columns and "MATNR" in mast.columns:
                for _, row in mast.iterrows():
                    bom_nr = _norm_stlnr(row["STLNR"])
                    parent = str(row["MATNR"]).strip()
                    if parent:
                        bom_parent_map[bom_nr] = parent
                logger.info(f"MAST loaded: {len(bom_parent_map)} material→BOM assignments")
            elif not stko.empty and "MATNR" in stko.columns:
                # OData extraction puts Material → MATNR on STKO headers
                for _, row in stko.iterrows():
                    bom_nr = _norm_stlnr(row["STLNR"])
                    parent = str(row.get("MATNR", "")).strip()
                    if parent:
                        bom_parent_map[bom_nr] = parent
                logger.info(f"STKO.MATNR fallback: {len(bom_parent_map)} parent assignments from BOM headers")
            else:
                logger.warning(
                    "Neither MAST nor STKO.MATNR available — cannot resolve BOM parent materials. "
                    "Add MAST to extraction to populate product_bom. "
                    "Skipping BOM creation."
                )
                # Without MAST, we cannot create correct BOMs — skip entirely
                # rather than creating self-referential entries

            # Enrich with header base quantity from STKO
            base_qty_map = {}
            if not stko.empty and "STLNR" in stko.columns:
                for _, row in stko.iterrows():
                    bom_nr = _norm_stlnr(row["STLNR"])
                    base_qty_map[bom_nr] = float(pd.to_numeric(row.get("BMENG", 1), errors="coerce") or 1)

            # Create BOM entries (only when MAST is available)
            if bom_parent_map:
                seen_bom_pairs: set = set()
                for _, row in stpo.iterrows():
                    bom_nr = _norm_stlnr(row["STLNR"])
                    component_mat = str(row.get("IDNRK", "")).strip()
                    parent_mat = bom_parent_map.get(bom_nr)

                    if not parent_mat or not component_mat:
                        continue
                    if parent_mat not in self._products or component_mat not in self._products:
                        continue
                    # Avoid self-referential BOMs
                    if parent_mat == component_mat:
                        continue
                    # Deduplicate
                    pair_key = (parent_mat, component_mat)
                    if pair_key in seen_bom_pairs:
                        continue
                    seen_bom_pairs.add(pair_key)

                    base_qty = base_qty_map.get(bom_nr, 1.0)
                    comp_qty = float(pd.to_numeric(row.get("MENGE", 1), errors="coerce") or 1)
                    scrap_pct = float(pd.to_numeric(row.get("AUSCH", 0), errors="coerce") or 0)

                    bom = ProductBom(
                        config_id=self._config.id,
                        product_id=f"{prefix}{parent_mat}",
                        component_product_id=f"{prefix}{component_mat}",
                        component_quantity=comp_qty / base_qty if base_qty else comp_qty,
                        scrap_percentage=scrap_pct,
                        source="SAP_STPO",
                    )
                    self.db.add(bom)
                    bom_count += 1

        # ProductionProcess from PLKO/PLPO
        plko = self._data.get("PLKO", pd.DataFrame())
        plpo = self._data.get("PLPO", pd.DataFrame())
        if not plpo.empty:
            proc_df = self.mapper.map_production_process(plko, plpo)
            seen_pp: set = set()
            for _, row in proc_df.iterrows():
                if row.get("site_id") in self._sites:
                    proc_id = str(row.get("process_id", f"PROC_{bom_count}"))
                    op_num = str(row.get("operation_number", "0"))
                    pp_key = f"CFG{self._config.id}_{proc_id}_{op_num}"
                    if pp_key in seen_pp:
                        continue
                    seen_pp.add(pp_key)
                    pp = ProductionProcess(
                        id=pp_key,
                        config_id=self._config.id,
                        site_id=self._sites[row["site_id"]].id,
                        setup_time=float(row.get("setup_time", 0) or 0),
                        operation_time=float(row.get("machine_time", 0) or 0),
                        source="SAP_PLPO",
                    )
                    self.db.add(pp)

        await self.db.flush()
        logger.info(f"Created {bom_count} BOM entries")
        return bom_count

    # ------------------------------------------------------------------
    # Step 8: Planning Data
    # ------------------------------------------------------------------

    async def _create_forecasts(self, horizon_weeks: int = 52) -> int:
        """Create Forecast entities from APO SNP data."""
        count = 0
        prefix = f"CFG{self._config.id}_"

        snpfc = self._data.get("/SAPAPO/SNPFC", pd.DataFrame())
        snpbv = self._data.get("/SAPAPO/SNPBV", pd.DataFrame())

        # Use SNPFC first, fallback to SNPBV
        forecast_data = snpfc if not snpfc.empty else snpbv

        if forecast_data.empty:
            logger.info("No forecast data available")
            return 0

        mat_col = "MATNR" if "MATNR" in forecast_data.columns else None
        loc_col = "LOCNO" if "LOCNO" in forecast_data.columns else None
        qty_col = next(
            (c for c in ["DEMAND_QTY", "FORECAST_QTY", "QUANTITY"] if c in forecast_data.columns),
            None,
        )

        if not mat_col or not loc_col or not qty_col:
            logger.warning("Forecast data missing required columns")
            return 0

        for _, row in forecast_data.iterrows():
            mat_key = str(row[mat_col]).strip()
            loc_key = str(row[loc_col]).strip()
            qty = float(pd.to_numeric(row.get(qty_col, 0), errors="coerce") or 0)

            if mat_key in self._products and loc_key in self._sites:
                forecast = Forecast(
                    config_id=self._config.id,
                    product_id=f"{prefix}{mat_key}",
                    site_id=self._sites[loc_key].id,
                    forecast_date=datetime.utcnow().date(),
                    forecast_quantity=qty,
                    forecast_p50=qty,
                    forecast_p10=round(qty * 0.7, 2),
                    forecast_p90=round(qty * 1.3, 2),
                    source="SAP_SNP",
                )
                self.db.add(forecast)
                count += 1

        await self.db.flush()
        logger.info(f"Created {count} forecast records")
        return count

    async def _create_inventory(
        self,
        default_policy: str = "doc_dem",
        safety_days: int = 14,
    ) -> int:
        """Create InvLevel and InvPolicy from MARD data.

        Also populates erp_planning_params JSONB on InvPolicy from MARC data
        when available, closing the data-loss gap identified in DIGITAL_TWIN.md §8C.
        """
        count = 0
        prefix = f"CFG{self._config.id}_"

        mard = self._data.get("MARD", pd.DataFrame())
        if mard.empty:
            return 0

        # Build MARC lookup for enriching InvPolicy with planning params
        marc = self._data.get("MARC", pd.DataFrame())
        marc_lookup: dict = {}
        if not marc.empty:
            for _, mrow in marc.iterrows():
                mk = (str(mrow.get("MATNR", "")).strip(), str(mrow.get("WERKS", "")).strip())
                marc_lookup[mk] = mrow

        for _, row in mard.iterrows():
            mat_key = str(row.get("MATNR", "")).strip()
            site_key = str(row.get("WERKS", "")).strip()

            if mat_key not in self._products or site_key not in self._sites:
                continue

            product_id = f"{prefix}{mat_key}"
            site_id = self._sites[site_key].id
            qty = float(pd.to_numeric(row.get("LABST", 0), errors="coerce") or 0)

            inv = InvLevel(
                config_id=self._config.id,
                product_id=product_id,
                site_id=site_id,
                on_hand_qty=qty,
                inventory_date=datetime.utcnow().date(),
            )
            self.db.add(inv)

            # Create inventory policy enriched with MARC planning params
            marc_row = marc_lookup.get((mat_key, site_key))
            erp_params = None
            extra_fields = {}

            if marc_row is not None:
                # Extract MARC fields that have dedicated InvPolicy columns
                eisbe = float(pd.to_numeric(marc_row.get("EISBE", 0), errors="coerce") or 0)
                minbe = float(pd.to_numeric(marc_row.get("MINBE", 0), errors="coerce") or 0)
                mabst = float(pd.to_numeric(marc_row.get("MABST", 0), errors="coerce") or 0)
                losgr = float(pd.to_numeric(marc_row.get("LOSGR", 0), errors="coerce") or 0)
                bstmi = float(pd.to_numeric(marc_row.get("BSTMI", 0), errors="coerce") or 0)
                bstma = float(pd.to_numeric(marc_row.get("BSTMA", 0), errors="coerce") or 0)
                bstrf = float(pd.to_numeric(marc_row.get("BSTRF", 0), errors="coerce") or 0)

                if eisbe > 0:
                    extra_fields["ss_quantity"] = eisbe
                    extra_fields["ss_policy"] = "abs_level"
                if minbe > 0:
                    extra_fields["reorder_point"] = minbe
                if mabst > 0:
                    extra_fields["order_up_to_level"] = mabst
                if losgr > 0:
                    extra_fields["fixed_order_quantity"] = losgr
                if bstmi > 0:
                    extra_fields["min_order_quantity"] = bstmi
                if bstma > 0:
                    extra_fields["max_order_quantity"] = bstma
                if bstrf > 0:
                    extra_fields["fixed_order_quantity"] = bstrf

                # Store all MARC planning fields in JSONB extension
                erp_params = {
                    k: v for k, v in {
                        "DISMM": str(marc_row.get("DISMM", "")).strip(),
                        "DISLS": str(marc_row.get("DISLS", "")).strip(),
                        "VRMOD": str(marc_row.get("VRMOD", "")).strip(),
                        "VINT1": int(pd.to_numeric(marc_row.get("VINT1", 0), errors="coerce") or 0),
                        "VINT2": int(pd.to_numeric(marc_row.get("VINT2", 0), errors="coerce") or 0),
                        "FXHOR": int(pd.to_numeric(marc_row.get("FXHOR", 0), errors="coerce") or 0),
                        "STRGR": str(marc_row.get("STRGR", "")).strip(),
                        "BESKZ": str(marc_row.get("BESKZ", "")).strip(),
                        "DISPO": str(marc_row.get("DISPO", "")).strip(),
                    }.items() if v
                }

            policy = InvPolicy(
                config_id=self._config.id,
                product_id=product_id,
                site_id=site_id,
                ss_policy=extra_fields.get("ss_policy", default_policy),
                ss_quantity=extra_fields.get("ss_quantity"),
                ss_days=safety_days if "ss_quantity" not in extra_fields else None,
                reorder_point=extra_fields.get("reorder_point"),
                order_up_to_level=extra_fields.get("order_up_to_level"),
                fixed_order_quantity=extra_fields.get("fixed_order_quantity"),
                min_order_quantity=extra_fields.get("min_order_quantity"),
                max_order_quantity=extra_fields.get("max_order_quantity"),
                erp_planning_params=erp_params if erp_params else None,
                is_active="true",
            )
            self.db.add(policy)
            count += 1

        await self.db.flush()
        logger.info(f"Created {count} inventory + policy records")
        return count

    # ------------------------------------------------------------------
    # Step 9: Transactional Data
    # ------------------------------------------------------------------

    @staticmethod
    def _jest_to_production_status(statuses: set) -> str:
        """Map JEST system statuses to ProductionOrder status.
        Priority order (highest lifecycle state wins):
          I0046 CLSD → CLOSED,  I0045 TECO → COMPLETED,
          I0009 CNF  → IN_PROGRESS,  I0002 REL  → RELEASED,
          I0001 CRTD → PLANNED
        """
        if "I0046" in statuses:
            return "CLOSED"
        if "I0045" in statuses:
            return "COMPLETED"
        if "I0009" in statuses:
            return "IN_PROGRESS"
        if "I0002" in statuses:
            return "RELEASED"
        return "PLANNED"

    @staticmethod
    def _gbstk_to_outbound_status(gbstk: str) -> str:
        """Map VBAK.GBSTK (overall status) to OutboundOrderLine status."""
        return {"A": "CONFIRMED", "B": "PARTIALLY_FULFILLED", "C": "FULFILLED"}.get(
            str(gbstk).strip(), "CONFIRMED"
        )

    @staticmethod
    def _elikz_to_inbound_status(elikz: str) -> str:
        """Map EKPO.ELIKZ (delivery completed indicator) to InboundOrder status."""
        return "RECEIVED" if str(elikz).strip() == "X" else "CONFIRMED"

    def _build_jest_status_map(self) -> Dict[str, set]:
        """Build OBJNR → set of active system statuses from JEST table."""
        jest = self._data.get("JEST", pd.DataFrame())
        if jest.empty:
            return {}
        result: Dict[str, set] = {}
        for _, row in jest.iterrows():
            objnr = str(row.get("OBJNR", "")).strip()
            stat = str(row.get("STAT", "")).strip()
            inact = str(row.get("INACT", "")).strip()
            if objnr and stat and not inact:
                result.setdefault(objnr, set()).add(stat)
        return result

    def _get_product_id(self, matnr: str) -> Optional[str]:
        """Resolve SAP MATNR to our Product.id (with config prefix).

        Tries exact match first, then leading-zero-stripped match.
        PLNBEZ in AFKO may have different zero-padding than MATNR in MARA.
        """
        raw_key = str(matnr).strip()
        if raw_key in self._products:
            return self._products[raw_key].id
        # Try with leading zeros stripped (PLNBEZ often has extra padding)
        stripped = raw_key.lstrip("0") or "0"
        if stripped != raw_key and stripped in self._products:
            return self._products[stripped].id
        # Try matching against stripped versions of product keys
        for pkey, product in self._products.items():
            if pkey.lstrip("0") == stripped:
                return product.id
        return None

    def _get_site_id(self, plant_code: str) -> Optional[int]:
        """Resolve SAP plant code to our Site.id."""
        code = str(plant_code).strip()
        for key, site in self._sites.items():
            sap_code = (site.attributes or {}).get("sap_plant_code", "")
            if sap_code == code or key == code:
                return site.id
        return None

    def _get_first_plant_site_id(self) -> Optional[int]:
        """Get the first plant site ID as fallback."""
        for site in self._sites.values():
            if site.master_type in ("MANUFACTURER", "INVENTORY"):
                return site.id
        return None

    async def _step_transactional(self, result: "StepResult", opts: Dict[str, Any]) -> int:
        """Execute step 9: Transactional Data (orders, production orders, quality orders)."""
        counts = await self._create_transactional_data(opts)
        total = sum(counts.values())

        result.sample_data.append(counts)
        result.anomalies = self._detect_transactional_anomalies()
        return total

    async def _create_transactional_data(self, opts: Dict[str, Any] = None) -> Dict[str, int]:
        """Create all transactional data entities from SAP extracts."""
        opts = opts or {}
        counts: Dict[str, int] = {}

        # Clean up prior SAP-imported transactional data to avoid PK/unique collisions on re-runs
        await self.db.execute(sql_text(
            "DELETE FROM inbound_order_line WHERE order_id IN "
            "(SELECT id FROM inbound_order WHERE source = 'SAP_IMPORT' AND config_id != :cid)"
        ), {"cid": self._config.id})
        await self.db.execute(sql_text(
            "DELETE FROM inbound_order WHERE source = 'SAP_IMPORT' AND config_id != :cid"
        ), {"cid": self._config.id})
        await self.db.execute(sql_text(
            "DELETE FROM production_order_components WHERE production_order_id IN "
            "(SELECT id FROM production_orders WHERE config_id != :cid AND order_number LIKE 'SAP-MO-%%')"
        ), {"cid": self._config.id})
        await self.db.execute(sql_text(
            "DELETE FROM production_orders WHERE config_id != :cid AND order_number LIKE 'SAP-MO-%%'"
        ), {"cid": self._config.id})
        await self.db.flush()

        if opts.get("include_outbound_orders", True):
            counts["outbound_orders"] = await self._create_outbound_orders(
                max_records=opts.get("max_outbound_orders", 5000)
            )
        if opts.get("include_inbound_orders", True):
            counts["inbound_orders"] = await self._create_inbound_orders(
                max_records=opts.get("max_inbound_orders", 2000)
            )
        if opts.get("include_production_orders", True):
            counts["production_orders"] = await self._create_production_orders()
        if opts.get("include_quality_orders", True):
            counts["quality_orders"] = await self._create_quality_orders()

        # Goods movements → Shipment records + InvLevel in-transit updates
        if opts.get("include_goods_movements", True):
            gm_counts = await self._create_goods_movements()
            counts.update(gm_counts)

        # Production order confirmations → actual quantities
        if opts.get("include_production_confirmations", True):
            conf_count = await self._create_production_confirmations()
            if conf_count > 0:
                counts["production_confirmations"] = conf_count

        # Also try PIR forecasts if step 8 didn't find APO data
        if opts.get("include_pir_forecasts", True):
            pir_count = await self._create_pir_forecasts()
            if pir_count > 0:
                counts["pir_forecasts"] = pir_count

        return counts

    async def _create_outbound_orders(self, max_records: int = 5000) -> int:
        """Create OutboundOrder + OutboundOrderLine from SAP sales orders (VBAK/VBAP)."""

        vbak = self._data.get("VBAK", pd.DataFrame())
        vbap = self._data.get("VBAP", pd.DataFrame())
        if vbap.empty:
            return 0

        # Build SO header map
        so_map: Dict[str, pd.Series] = {}
        if not vbak.empty and "VBELN" in vbak.columns:
            for _, row in vbak.iterrows():
                so_map[str(row.get("VBELN", "")).strip()] = row

        first_plant_id = self._get_first_plant_site_id()
        created_headers: set = set()
        count = 0

        for _, item in vbap.iterrows():
            if count >= max_records:
                break
            vbeln = str(item.get("VBELN", "")).strip()
            matnr = str(item.get("MATNR", "")).strip()
            werks = str(item.get("WERKS", "")).strip()

            product_id = self._get_product_id(matnr)
            if not product_id:
                continue

            site_id = self._get_site_id(werks) or first_plant_id
            if not site_id:
                continue

            so = so_map.get(vbeln, pd.Series())
            gbstk = str(so.get("GBSTK", "A")).strip() if not so.empty else "A"
            status = self._gbstk_to_outbound_status(gbstk)

            order_date_str = str(so.get("ERDAT", "")).strip() if not so.empty else ""
            delivery_date_str = str(so.get("VDATU", "")).strip() if not so.empty else ""
            order_date = self._parse_sap_date(order_date_str)
            delivery_date = self._parse_sap_date(delivery_date_str) or order_date or datetime.utcnow().date()

            qty = float(pd.to_numeric(item.get("KWMENG", 0), errors="coerce") or 0)
            net_value = float(pd.to_numeric(item.get("NETWR", 0), errors="coerce") or 0)
            currency = str(so.get("WAERK", "USD")).strip() if not so.empty else "USD"
            customer_id = str(so.get("KUNNR", "")).strip() if not so.empty else ""

            # Create parent OutboundOrder header (once per SO)
            order_id = f"SAP-SO-{vbeln}"
            if order_id not in created_headers:
                total_value = float(pd.to_numeric(so.get("NETWR", 0), errors="coerce") or 0) if not so.empty else 0
                ob_header = OutboundOrder(
                    id=order_id,
                    order_type="SALES",
                    customer_id=customer_id,
                    ship_from_site_id=site_id,
                    status=status,
                    order_date=order_date or datetime.utcnow().date(),
                    requested_delivery_date=delivery_date,
                    total_value=total_value,
                    currency=currency,
                    priority="STANDARD",
                    config_id=self._config.id,
                    source="SAP_IMPORT",
                    source_event_id=f"SO-{vbeln}",
                    source_update_dttm=datetime.utcnow(),
                )
                self.db.add(ob_header)
                created_headers.add(order_id)

            ob = OutboundOrderLine(
                order_id=order_id,
                line_number=int(pd.to_numeric(item.get("POSNR", 1), errors="coerce") or 1),
                product_id=product_id,
                site_id=site_id,
                ordered_quantity=qty,
                requested_delivery_date=delivery_date,
                order_date=order_date or datetime.utcnow().date(),
                config_id=self._config.id,
                status=status,
                priority_code="STANDARD",
            )
            self.db.add(ob)
            count += 1

        await self.db.flush()
        logger.info(f"Created {count} outbound order lines (status from VBAK.GBSTK)")
        return count

    async def _create_inbound_orders(self, max_records: int = 2000) -> int:
        """Create InboundOrder + InboundOrderLine records from SAP POs (EKKO/EKPO)."""
        ekko = self._data.get("EKKO", pd.DataFrame())
        ekpo = self._data.get("EKPO", pd.DataFrame())
        if ekko.empty:
            return 0

        first_plant_id = self._get_first_plant_site_id()
        count = 0

        for _, po in ekko.iterrows():
            if count >= max_records:
                break
            ebeln = str(po.get("EBELN", "")).strip()

            order_date = self._parse_sap_date(str(po.get("BEDAT", "")).strip())

            # Get line items
            items = ekpo[ekpo["EBELN"].astype(str).str.strip() == ebeln] if not ekpo.empty and "EBELN" in ekpo.columns else pd.DataFrame()
            if items.empty:
                continue

            first_item = items.iloc[0]
            werks = str(first_item.get("WERKS", "")).strip()
            dest_site_id = self._get_site_id(werks) or first_plant_id
            if not dest_site_id:
                continue

            # Determine header status from line items' ELIKZ
            if "ELIKZ" in items.columns:
                elikz_vals = items["ELIKZ"].astype(str).str.strip()
                all_received = (elikz_vals == "X").all()
                any_received = (elikz_vals == "X").any()
            else:
                all_received = False
                any_received = False

            if all_received:
                ib_status = "RECEIVED"
            elif any_received:
                ib_status = "PARTIALLY_RECEIVED"
            else:
                ib_status = "CONFIRMED"

            total_qty = float(pd.to_numeric(items["MENGE"], errors="coerce").fillna(0).sum()) if "MENGE" in items.columns else 0

            ib_order = InboundOrder(
                id=f"SAP-PO-{ebeln}",
                order_type="PURCHASE",
                ship_to_site_id=dest_site_id,
                status=ib_status,
                order_date=order_date or datetime.utcnow().date(),
                total_ordered_qty=total_qty,
                config_id=self._config.id,
                source="SAP_IMPORT",
                source_event_id=f"PO-{ebeln}",
                source_update_dttm=datetime.utcnow(),
            )
            self.db.add(ib_order)

            for _, pi in items.iterrows():
                matnr = str(pi.get("MATNR", "")).strip()
                product_id = self._get_product_id(matnr)
                if not product_id:
                    continue

                line_status = self._elikz_to_inbound_status(str(pi.get("ELIKZ", "")))
                qty = float(pd.to_numeric(pi.get("MENGE", 0), errors="coerce") or 0)
                net_price = float(pd.to_numeric(pi.get("NETPR", 0), errors="coerce") or 0)

                ib_line = InboundOrderLine(
                    order_id=f"SAP-PO-{ebeln}",
                    line_number=int(pd.to_numeric(pi.get("EBELP", 1), errors="coerce") or 1),
                    product_id=product_id,
                    to_site_id=dest_site_id,
                    order_type="PURCHASE",
                    quantity_submitted=qty,
                    status=line_status,
                    cost=net_price if net_price else None,
                    config_id=self._config.id,
                    tenant_id=self.tenant_id,
                )
                self.db.add(ib_line)

            count += 1

        await self.db.flush()
        logger.info(f"Created {count} inbound orders (status from EKPO.ELIKZ)")
        return count

    async def _create_production_orders(self) -> int:
        """Create ProductionOrder + ProductionOrderComponent from AFKO/AFPO/JEST."""
        afko = self._data.get("AFKO", pd.DataFrame())
        if afko.empty:
            return 0

        afpo = self._data.get("AFPO", pd.DataFrame())
        resb = self._data.get("RESB", pd.DataFrame())
        jest_map = self._build_jest_status_map()

        # Pre-build AFPO material lookup for fallback product resolution
        afpo_by_aufnr: Dict[str, pd.DataFrame] = {}
        if not afpo.empty and "AUFNR" in afpo.columns:
            for aufnr_val, group in afpo.groupby(afpo["AUFNR"].astype(str).str.strip()):
                afpo_by_aufnr[aufnr_val] = group

        skipped_no_product = 0
        count = 0
        for _, po in afko.iterrows():
            aufnr = str(po.get("AUFNR", "")).strip()
            plnbez = str(po.get("PLNBEZ", "")).strip()

            # Try to resolve product: first from AFKO.PLNBEZ, then from AFPO.MATNR
            product_id = self._get_product_id(plnbez)
            if not product_id and aufnr in afpo_by_aufnr:
                # Fallback: use MATNR from AFPO line item
                afpo_matnr = str(afpo_by_aufnr[aufnr].iloc[0].get("MATNR", "")).strip()
                if afpo_matnr:
                    product_id = self._get_product_id(afpo_matnr)
            if not product_id:
                skipped_no_product += 1
                continue

            # Find plant from AFPO — check PWERK (canonical), DESSION (HANA variant), WERKS
            site_id = None
            if aufnr in afpo_by_aufnr:
                afpo_row = afpo_by_aufnr[aufnr].iloc[0]
                for plant_col in ("PWERK", "DESSION", "WERKS"):
                    if plant_col in afpo_row.index:
                        werks = str(afpo_row.get(plant_col, "")).strip()
                        if werks:
                            site_id = self._get_site_id(werks)
                            if site_id:
                                break
            if not site_id:
                site_id = self._get_first_plant_site_id()
            if not site_id:
                continue

            # Map JEST status
            objnr = f"OR{aufnr.zfill(12)}"
            statuses = jest_map.get(objnr, set())
            mo_status = self._jest_to_production_status(statuses)

            # Quantities
            planned_qty = float(pd.to_numeric(po.get("GAMNG", 1), errors="coerce") or 1)
            actual_qty = None
            if aufnr in afpo_by_aufnr:
                afpo_match = afpo_by_aufnr[aufnr]
                wemng = float(pd.to_numeric(afpo_match.iloc[0].get("WEMNG", 0), errors="coerce") or 0)
                if wemng > 0:
                    actual_qty = int(wemng)
                pq = float(pd.to_numeric(afpo_match.iloc[0].get("PSMNG", 0), errors="coerce") or 0)
                if pq > 0:
                    planned_qty = pq

            # Dates
            start_date = self._parse_sap_date(str(po.get("GSTRS", "")).strip()) or \
                         self._parse_sap_date(str(po.get("GSTRP", "")).strip())
            end_date = self._parse_sap_date(str(po.get("GLTRP", "")).strip()) or \
                       self._parse_sap_date(str(po.get("GLTRS", "")).strip())
            today = datetime.utcnow().date()
            if not start_date:
                start_date = today
            if not end_date:
                end_date = start_date + timedelta(days=7)

            aufnr_clean = aufnr.lstrip("0") or "0"
            mo = ProductionOrder(
                order_number=f"SAP-MO-{aufnr_clean}",
                item_id=product_id,
                site_id=site_id,
                config_id=self._config.id,
                planned_quantity=int(planned_qty),
                actual_quantity=actual_qty,
                status=mo_status,
                planned_start_date=datetime.combine(start_date, datetime.min.time()),
                planned_completion_date=datetime.combine(end_date, datetime.min.time()),
                lead_time_planned=max(1, (end_date - start_date).days),
                priority=5,
                notes=f"JEST statuses: {','.join(sorted(statuses))}" if statuses else None,
                extra_data={"sap_aufnr": aufnr, "sap_objnr": objnr},
            )
            self.db.add(mo)
            await self.db.flush()
            count += 1

            # Add components from RESB reservations
            if not resb.empty and "AUFNR" in resb.columns:
                res_rows = resb[resb["AUFNR"].astype(str).str.strip() == aufnr]
                for _, res in res_rows.iterrows():
                    comp_matnr = str(res.get("MATNR", "")).strip()
                    comp_product_id = self._get_product_id(comp_matnr)
                    if not comp_product_id or comp_product_id == product_id:
                        continue
                    comp = ProductionOrderComponent(
                        production_order_id=mo.id,
                        component_item_id=comp_product_id,
                        planned_quantity=float(pd.to_numeric(res.get("BDMNG", 1), errors="coerce") or 1),
                        unit_of_measure=str(res.get("MEINS", "EA")).strip(),
                    )
                    self.db.add(comp)

        await self.db.flush()
        if skipped_no_product > 0:
            logger.info(f"Skipped {skipped_no_product} production orders (material not in products)")
        logger.info(f"Created {count} production orders (status from JEST)")
        return count

    async def _create_quality_orders(self) -> int:
        """Create QualityOrder records from QALS inspection lots."""
        # Check if the quality_order table exists (it may not have been migrated yet)
        result = await self.db.execute(sql_text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'quality_order' LIMIT 1"
        ))
        if not result.scalar():
            logger.info("quality_order table does not exist, skipping quality order creation")
            return 0

        qals = self._data.get("QALS", pd.DataFrame())
        if qals.empty:
            return 0

        origin_map = {
            "01": ("INCOMING", "GOODS_RECEIPT"),
            "02": ("IN_PROCESS", "PRODUCTION_ORDER"),
            "03": ("FINAL", "PRODUCTION_ORDER"),
            "04": ("RETURNS", "CUSTOMER_COMPLAINT"),
            "05": ("SAMPLING", "PREVENTIVE_SAMPLE"),
        }

        count = 0
        for _, ql in qals.iterrows():
            matnr = str(ql.get("MATNR", "")).strip()
            werks = str(ql.get("WERK", "")).strip()
            product_id = self._get_product_id(matnr)
            site_id = self._get_site_id(werks)
            if not product_id or not site_id:
                continue

            prueflos = str(ql.get("PRUEFLOS", "")).strip()
            art = str(ql.get("ART", "01")).strip()
            insp_type, origin_type = origin_map.get(art, ("INCOMING", "GOODS_RECEIPT"))

            bearbstatu = str(ql.get("BEARBSTATU", "")).strip()
            if bearbstatu:
                qo_status = "IN_INSPECTION"
            else:
                qo_status = "CREATED"
            if str(ql.get("INSMK", "")).strip():
                qo_status = "DISPOSITION_DECIDED"

            lot_clean = prueflos.lstrip("0") or "0"
            qo = QualityOrder(
                quality_order_number=f"SAP-QI-{lot_clean}",
                site_id=site_id,
                config_id=self._config.id,
                tenant_id=self.tenant_id,
                inspection_type=insp_type,
                status=qo_status,
                origin_type=origin_type,
                origin_order_id=str(ql.get("AUFNR", "")).strip(),
                product_id=product_id,
                lot_number=str(ql.get("CHARG", "")).strip(),
                inspection_quantity=float(pd.to_numeric(ql.get("LOSMENGE", 0), errors="coerce") or 0),
                source="SAP_IMPORT",
                source_event_id=f"QALS-{prueflos}",
                source_update_dttm=datetime.utcnow(),
            )
            self.db.add(qo)
            count += 1

        await self.db.flush()
        logger.info(f"Created {count} quality orders")
        return count

    async def _create_goods_movements(self) -> Dict[str, int]:
        """Create Shipment records from MSEG/MKPF and update InvLevel with in-transit quantities.

        SAP movement types mapped:
        - 101: Goods receipt for PO → shipment status 'delivered'
        - 121: Reversal of 101 → skip (handled by net calculation)
        - 201: Goods issue for cost center → consumption (not a shipment)
        - 261: Goods issue for production order → consumption (not a shipment)
        - 301: Transfer posting plant-to-plant → in_transit shipment
        - 303: Plant-to-plant transfer in same step → delivered transfer
        - 311: Transfer posting SLoc-to-SLoc (same plant) → internal, skip
        - 601: Goods issue for delivery (outbound) → in_transit shipment
        - 641: Returns → skip
        - 651: Returns delivery → skip
        - 653: Returns delivery reversal → skip
        - 101+316: Stock transfer receipt → clears in-transit
        """
        mseg = self._data.get("MSEG", pd.DataFrame())
        mkpf = self._data.get("MKPF", pd.DataFrame())
        if mseg.empty:
            return {}

        # Build MKPF header lookup: MBLNR → row (for posting dates)
        mkpf_map: Dict[str, pd.Series] = {}
        if not mkpf.empty and "MBLNR" in mkpf.columns:
            for _, row in mkpf.iterrows():
                mblnr = str(row.get("MBLNR", "")).strip()
                if mblnr:
                    mkpf_map[mblnr] = row

        # Movement types that represent shipments (inter-site material flow)
        SHIPMENT_MVTS = {
            "101": "delivered",       # GR for PO — vendor→plant, completed
            "301": "in_transit",      # Transfer posting plant-to-plant — in transit
            "303": "delivered",       # Plant-to-plant same step — completed
            "601": "in_transit",      # GI for delivery — plant→customer, in transit
        }

        # Clean up prior SAP-imported shipments for this config
        await self.db.execute(sql_text(
            "DELETE FROM shipment WHERE source = 'SAP_IMPORT' AND config_id = :cid"
        ), {"cid": self._config.id})
        await self.db.flush()

        shipment_count = 0
        # Track in-transit quantities per (product, site) for InvLevel updates
        in_transit_by_product_site: Dict[Tuple[str, int], float] = {}

        for _, row in mseg.iterrows():
            bwart = str(row.get("BWART", "")).strip()
            if bwart not in SHIPMENT_MVTS:
                continue

            matnr = str(row.get("MATNR", "")).strip()
            werks = str(row.get("WERKS", "")).strip()
            product_id = self._get_product_id(matnr)
            from_site_id = self._get_site_id(werks)
            if not product_id or not from_site_id:
                continue

            qty = float(pd.to_numeric(row.get("MENGE", 0), errors="coerce") or 0)
            if qty <= 0:
                continue

            mblnr = str(row.get("MBLNR", "")).strip()
            mjahr = str(row.get("MJAHR", "")).strip()
            zeile = str(row.get("ZEILE", row.get("ZEESSION", "1"))).strip()
            shkzg = str(row.get("SHKZG", "")).strip()  # S=debit(issue), H=credit(receipt)

            # Determine from/to sites based on movement type
            status = SHIPMENT_MVTS[bwart]
            to_site_id = from_site_id  # default

            if bwart in ("301", "303"):
                # Plant-to-plant transfer: UMWRK = receiving plant
                umwrk = str(row.get("UMWRK", "")).strip()
                if umwrk:
                    to_site_id = self._get_site_id(umwrk) or from_site_id
                if to_site_id == from_site_id:
                    continue  # Skip same-plant transfers
            elif bwart == "601":
                # Outbound delivery: to_site = customer (demand site)
                kunnr = str(row.get("KUNNR", "")).strip()
                if kunnr:
                    to_site_id = self._get_site_id(kunnr)
                if not to_site_id:
                    # Try to find any demand site
                    to_site_id = self._get_first_demand_site_id() or from_site_id
            elif bwart == "101":
                # GR for PO: from_site = vendor, to_site = plant (werks)
                lifnr = str(row.get("LIFNR", "")).strip()
                vendor_site_id = self._get_site_id(lifnr) if lifnr else None
                if vendor_site_id:
                    to_site_id = from_site_id
                    from_site_id = vendor_site_id
                else:
                    # vendor not mapped as site — use first supply site
                    supply_id = self._get_first_supply_site_id()
                    if supply_id:
                        to_site_id = from_site_id
                        from_site_id = supply_id

            # Get posting date from MKPF
            header = mkpf_map.get(mblnr, pd.Series())
            budat_str = str(row.get("BUDAT_MKPF", "")).strip()
            if not budat_str and not header.empty:
                budat_str = str(header.get("BUDAT", "")).strip()
            ship_date = self._parse_sap_date(budat_str)

            # PO reference for GR
            ebeln = str(row.get("EBELN", "")).strip()
            order_ref = f"SAP-PO-{ebeln}" if ebeln else f"SAP-MSEG-{mblnr}"

            shipment_id = f"SAP-GMA-{mblnr}-{zeile}"

            shipment = Shipment(
                id=shipment_id,
                description=f"SAP Mvt {bwart}: {matnr}",
                order_id=order_ref,
                order_line_number=int(pd.to_numeric(zeile, errors="coerce") or 1),
                product_id=product_id,
                quantity=qty,
                uom=str(row.get("MEINS", "EA")).strip(),
                from_site_id=from_site_id,
                to_site_id=to_site_id,
                status=status,
                ship_date=datetime.combine(ship_date, datetime.min.time()) if ship_date else None,
                config_id=self._config.id,
                tenant_id=self.tenant_id,
                source="SAP_IMPORT",
                source_event_id=f"MSEG-{mblnr}-{mjahr}-{zeile}",
                source_update_dttm=datetime.utcnow(),
            )
            self.db.add(shipment)
            shipment_count += 1

            # Track in-transit quantities
            if status == "in_transit":
                key = (product_id, to_site_id)
                in_transit_by_product_site[key] = in_transit_by_product_site.get(key, 0) + qty

        await self.db.flush()
        logger.info(f"Created {shipment_count} shipment records from MSEG goods movements")

        # Update InvLevel with in-transit quantities
        inv_updates = 0
        today = datetime.utcnow().date()
        for (product_id, site_id), transit_qty in in_transit_by_product_site.items():
            # Try to update existing InvLevel record
            result = await self.db.execute(sql_text(
                "UPDATE inv_level SET in_transit_qty = COALESCE(in_transit_qty, 0) + :qty "
                "WHERE product_id = :pid AND site_id = :sid AND config_id = :cid "
                "AND inventory_date = :dt"
            ), {"qty": transit_qty, "pid": product_id, "sid": site_id,
                "cid": self._config.id, "dt": today})
            if result.rowcount == 0:
                # Create new InvLevel record with in-transit
                inv = InvLevel(
                    product_id=product_id,
                    site_id=site_id,
                    config_id=self._config.id,
                    inventory_date=today,
                    on_hand_qty=0,
                    in_transit_qty=transit_qty,
                    source="SAP_IMPORT",
                    source_event_id="MSEG_TRANSIT",
                    source_update_dttm=datetime.utcnow(),
                )
                self.db.add(inv)
            inv_updates += 1

        await self.db.flush()
        logger.info(f"Updated {inv_updates} InvLevel records with in-transit quantities")

        return {"shipments": shipment_count, "inv_transit_updates": inv_updates}

    async def _create_production_confirmations(self) -> int:
        """Update ProductionOrder actual quantities from AFRU confirmations.

        AFRU contains time/quantity confirmations for MO operations:
        - LMNGA: Yield quantity (good output)
        - XMNGA: Scrap quantity
        - RMNGA: Rework quantity
        - ISM01-ISM06: Activity quantities (machine time, labor time, etc.)
        """
        afru = self._data.get("AFRU", pd.DataFrame())
        if afru.empty:
            return 0

        count = 0
        # Aggregate yield by AUFNR
        for aufnr, grp in afru.groupby(afru["AUFNR"].astype(str).str.strip()):
            aufnr_clean = aufnr.lstrip("0") or "0"
            order_number = f"SAP-MO-{aufnr_clean}"

            yield_qty = float(pd.to_numeric(grp.get("LMNGA", pd.Series()), errors="coerce").fillna(0).sum())
            scrap_qty = float(pd.to_numeric(grp.get("XMNGA", pd.Series()), errors="coerce").fillna(0).sum())

            if yield_qty <= 0 and scrap_qty <= 0:
                continue

            result = await self.db.execute(sql_text(
                "UPDATE production_orders SET actual_quantity = :yield, "
                "extra_data = CAST(:scrap_json AS json) "
                "WHERE order_number = :on AND config_id = :cid"
            ), {
                "yield": int(yield_qty),
                "scrap_json": json.dumps({"sap_scrap_qty": scrap_qty, "sap_yield_qty": yield_qty}),
                "on": order_number,
                "cid": self._config.id,
            })
            if result.rowcount > 0:
                count += 1

        await self.db.flush()
        logger.info(f"Updated {count} production orders with AFRU confirmations")
        return count

    def _get_first_demand_site_id(self) -> Optional[int]:
        """Get ID of first CUSTOMER site in config."""
        for key, site in self._sites.items():
            mt = getattr(site, "master_type", "")
            if mt == "CUSTOMER":
                return site.id
        return None

    def _get_first_supply_site_id(self) -> Optional[int]:
        """Get ID of first VENDOR site in config."""
        for key, site in self._sites.items():
            mt = getattr(site, "master_type", "")
            if mt == "VENDOR":
                return site.id
        return None

    async def _create_pir_forecasts(self) -> int:
        """Create Forecast records from SAP Planned Independent Requirements (PBIM/PBED).

        Falls back to this when APO SNP data is not available.
        Handles both canonical column name (BDZEI) and HANA-extracted variant (BESSION).
        """
        pbim = self._data.get("PBIM", pd.DataFrame())
        pbed = self._data.get("PBED", pd.DataFrame())
        if pbed.empty:
            return 0

        # Resolve the PIR key column — canonical SAP name is BDZEI, but
        # some HANA extracts produce BESSION instead.
        pir_key_col = "BDZEI"
        if not pbim.empty:
            if "BDZEI" in pbim.columns:
                pir_key_col = "BDZEI"
            elif "BESSION" in pbim.columns:
                pir_key_col = "BESSION"
                logger.info("PBIM uses BESSION column (HANA variant) instead of BDZEI")
            else:
                logger.warning(f"PBIM has no BDZEI or BESSION column — columns: {list(pbim.columns)}")
                return 0

        # Resolve key column in PBED too
        pbed_key_col = pir_key_col  # should match PBIM
        if pir_key_col not in pbed.columns:
            # Try the other variant
            alt = "BESSION" if pir_key_col == "BDZEI" else "BDZEI"
            if alt in pbed.columns:
                pbed_key_col = alt
            else:
                logger.warning(f"PBED has no BDZEI or BESSION column — columns: {list(pbed.columns)}")
                return 0

        # Build PIR header map: key → {MATNR, WERKS}
        header_map: Dict[str, pd.Series] = {}
        if not pbim.empty:
            for _, row in pbim.iterrows():
                key_val = str(row.get(pir_key_col, "")).strip()
                if key_val:
                    header_map[key_val] = row

        if not header_map:
            logger.warning("PBIM header map is empty — no PIR forecasts can be created")
            return 0

        # Date-shift: IDES data has 2017-era dates; shift forward to current year
        today = datetime.utcnow().date()
        year_offset = 0  # will be computed from first valid date

        count = 0
        for _, sched in pbed.iterrows():
            key_val = str(sched.get(pbed_key_col, "")).strip()
            header = header_map.get(key_val)
            if header is None:
                continue

            matnr = str(header.get("MATNR", "")).strip()
            werks = str(header.get("WERKS", "")).strip()
            product_id = self._get_product_id(matnr)
            site_id = self._get_site_id(werks)
            if not product_id or not site_id:
                continue

            fc_date = self._parse_sap_date(str(sched.get("PDATU", "")).strip())
            qty = float(pd.to_numeric(sched.get("PLNMG", 0), errors="coerce") or 0)
            if not fc_date or qty <= 0:
                continue

            # Auto-detect year offset on first valid date (IDES dates are typically 2017-era)
            if year_offset == 0 and fc_date.year < today.year - 1:
                year_offset = today.year - fc_date.year
                logger.info(f"PIR date-shift: detected {fc_date.year}-era data, shifting +{year_offset} years to {today.year}")

            # Apply date shift
            if year_offset > 0:
                try:
                    fc_date = fc_date.replace(year=fc_date.year + year_offset)
                except ValueError:
                    # Handle Feb 29 in non-leap year
                    fc_date = fc_date.replace(month=2, day=28, year=fc_date.year + year_offset)

            # PIR provides planned quantity; estimate P10/P90 at ±20% CV
            std = max(qty * 0.2, 1.0)
            fc = Forecast(
                product_id=product_id,
                site_id=site_id,
                config_id=self._config.id,
                forecast_date=fc_date,
                forecast_quantity=round(qty, 2),
                forecast_p10=round(max(0, qty - 1.28 * std), 2),
                forecast_p50=round(qty, 2),
                forecast_p90=round(qty + 1.28 * std, 2),
                source="SAP_PIR",
            )
            self.db.add(fc)
            count += 1

        await self.db.flush()
        if count > 0:
            logger.info(f"Created {count} forecast records from SAP PIR (PBIM/PBED)")
        return count

    @staticmethod
    def _parse_sap_date(val: str) -> Optional[date]:
        """Parse SAP date formats: YYYYMMDD or YYYY-MM-DD."""
        if not val or val == "00000000" or val == "nan" or len(val) < 8:
            return None
        try:
            if "-" in val:
                return datetime.strptime(val[:10], "%Y-%m-%d").date()
            return datetime.strptime(val[:8], "%Y%m%d").date()
        except (ValueError, TypeError):
            return None

    def _detect_transactional_anomalies(self) -> List[Dict[str, Any]]:
        """Detect anomalies in transactional data."""
        anomalies = []
        vbap = self._data.get("VBAP", pd.DataFrame())
        ekko = self._data.get("EKKO", pd.DataFrame())
        afko = self._data.get("AFKO", pd.DataFrame())

        if vbap.empty:
            anomalies.append({"type": "missing_data", "message": "No sales order items (VBAP) — outbound orders skipped"})
        if ekko.empty:
            anomalies.append({"type": "missing_data", "message": "No purchase order headers (EKKO) — inbound orders skipped"})
        if afko.empty:
            anomalies.append({"type": "missing_data", "message": "No production orders (AFKO) — production orders skipped"})

        jest = self._data.get("JEST", pd.DataFrame())
        if afko is not None and not afko.empty and jest.empty:
            anomalies.append({"type": "warning", "message": "Production orders found but no JEST status data — all orders will default to PLANNED status"})

        return anomalies

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _create_config(self, config_name: str) -> SupplyChainConfig:
        """Create the SupplyChainConfig record.

        Deactivates any existing active configs for this tenant first,
        ensuring only one active SAP-imported config exists at a time.
        """
        # Deactivate only previous SAP-imported configs (preserve learning/Beer Game configs)
        await self.db.execute(
            sql_text(
                "UPDATE supply_chain_configs SET is_active = false "
                "WHERE tenant_id = :tid AND is_active = true "
                "AND description LIKE 'Imported from SAP%%'"
            ),
            {"tid": self.tenant_id},
        )

        config = SupplyChainConfig(
            name=config_name,
            description=f"Imported from SAP data on {datetime.utcnow().strftime('%Y-%m-%d')}",
            tenant_id=self.tenant_id,
            is_active=True,
        )
        self.db.add(config)
        await self.db.flush()
        logger.info(f"Created SC config: {config.name} (id={config.id})")
        return config
