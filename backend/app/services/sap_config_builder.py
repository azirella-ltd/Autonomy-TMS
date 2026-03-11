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
    OutboundOrderLine, InboundOrder, InboundOrderLine,
)
from app.models.production_order import ProductionOrder, ProductionOrderComponent
from app.models.quality_order import QualityOrder
from app.models.supplier import VendorProduct, VendorLeadTime
from app.models.tenant import Tenant

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


# Master type constants
MASTER_MANUFACTURER = "MANUFACTURER"
MASTER_VENDOR = "VENDOR"
MASTER_CUSTOMER = "CUSTOMER"
MASTER_INVENTORY = "INVENTORY"
# Legacy aliases kept for backward compatibility with existing DB rows
MASTER_MARKET_SUPPLY = "MARKET_SUPPLY"
MASTER_MARKET_DEMAND = "MARKET_DEMAND"


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
    5: "Transportation Lanes",
    6: "Partners & Sourcing",
    7: "BOM & Manufacturing",
    8: "Planning Data",
    9: "Transactional Data",
}

STEP_ENTITY_TYPES = {
    1: "validation",
    2: "geography",
    3: "site",
    4: "product",
    5: "transportation_lane",
    6: "trading_partner",
    7: "product_bom",
    8: "forecast",
    9: "orders",
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

        try:
            # Step 1: Create config (also deactivates previous active configs)
            self._config = await self._create_config(config_name)

            # Step 2: Company & Geography
            await self._create_geography()

            # Step 3: Sites
            site_count = await self._create_sites(overrides, opts)

            # Step 4: Products
            product_count = await self._create_products()

            # Step 5: Transportation Lanes
            lane_count = await self._create_lanes()

            # Step 6: Trading Partners & Sourcing
            vendor_count, customer_count, sourcing_count = await self._create_partners_and_sourcing()

            # Step 7: BOM & Manufacturing
            bom_count = await self._create_bom_and_manufacturing()

            # Step 8: Planning Data
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
            order_counts = await self._create_transactional_data(opts)

            await self.db.commit()

            return {
                "config_id": self._config.id,
                "config_name": config_name,
                "summary": {
                    "sites": site_count,
                    "products": product_count,
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
            count = await self._step_lanes(result)
        elif step == 6:
            count = await self._step_partners(result)
        elif step == 7:
            count = await self._step_bom(result)
        elif step == 8:
            count = await self._step_planning(result, opts)
        elif step == 9:
            count = await self._step_transactional(result, opts)
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
                summary["lanes"] = await self._step_lanes(result)
            elif step_num == 6:
                summary["partners"] = await self._step_partners(result)
            elif step_num == 7:
                summary["bom"] = await self._step_bom(result)
            elif step_num == 8:
                summary["planning"] = await self._step_planning(result, opts)
            elif step_num == 9:
                summary["transactional"] = await self._step_transactional(result, opts)
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
        if opts.get("include_forecasts", True):
            forecast_count = await self._create_forecasts(
                horizon_weeks=opts.get("forecast_horizon_weeks", 52)
            )
        if opts.get("include_inventory", True):
            inv_count = await self._create_inventory(
                default_policy=opts.get("default_inv_policy", "doc_dem"),
                safety_days=opts.get("default_safety_days", 14),
            )

        result.sample_data.append({
            "forecasts_created": forecast_count,
            "inventory_records_created": inv_count,
            "policy_type": opts.get("default_inv_policy", "doc_dem"),
            "safety_days": opts.get("default_safety_days", 14),
        })

        result.anomalies = self._detect_planning_anomalies()
        return forecast_count + inv_count

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
        """Apply plant and company filters to all DataFrames."""
        if not plant_filter and not company_filter:
            return

        for table_name, df in list(self._data.items()):
            if df.empty:
                continue
            filtered = df
            if plant_filter and "WERKS" in df.columns:
                filtered = filtered[filtered["WERKS"].isin(plant_filter)]
            if company_filter and "BUKRS" in df.columns:
                filtered = filtered[filtered["BUKRS"] == company_filter]
            self._data[table_name] = filtered

    # ------------------------------------------------------------------
    # Step 2: Company & Geography
    # ------------------------------------------------------------------

    async def _create_geography(self):
        """Create Geography entities from ADRC addresses (upsert, deduplicated).

        Geocodes addresses to lat/lon using Nominatim when coordinates are not
        already available from SAP.
        """
        adrc = self._data.get("ADRC", pd.DataFrame())
        if adrc.empty:
            return

        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from app.services.geocoding_service import geocode_batch

        geo_df = self.mapper.map_geography(adrc)
        # Deduplicate by id — last occurrence wins
        seen: Dict[str, dict] = {}
        for _, row in geo_df.iterrows():
            geo_id = str(row.get("address_id", ""))
            key = f"{self._config.id}_{geo_id}"
            seen[key] = {
                "id": key,
                "description": str(row.get("name", "")),
                "address_1": str(row.get("street", "")),
                "city": str(row.get("city", "")),
                "state_prov": str(row.get("region", "")),
                "country": str(row.get("country", "")),
                "postal_code": str(row.get("postal_code", "")),
            }

        rows = list(seen.values())

        # Geocode addresses to populate lat/lon
        if rows:
            address_inputs = [
                {
                    "street": r.get("address_1", ""),
                    "city": r.get("city", ""),
                    "state": r.get("state_prov", ""),
                    "country": r.get("country", ""),
                    "postal_code": r.get("postal_code", ""),
                }
                for r in rows
            ]
            try:
                coords = await geocode_batch(address_inputs)
                geocoded = 0
                for row, coord in zip(rows, coords):
                    if coord:
                        row["latitude"] = coord[0]
                        row["longitude"] = coord[1]
                        geocoded += 1
                logger.info(f"Geocoded {geocoded}/{len(rows)} geography records")
            except Exception as e:
                logger.warning(f"Geocoding batch failed, continuing without coordinates: {e}")

        if rows:
            stmt = pg_insert(Geography).values(rows)
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

        logger.info(f"Upserted {len(rows)} geography records")

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
            {"type": "SUPPLIER", "label": "Vendor", "order": 2, "master_type": "VENDOR"},
            {"type": "CUSTOMER", "label": "Customer", "order": 3, "master_type": "CUSTOMER", "tpartner_type": "customer", "is_external": True},
        ]
        self._config.site_type_definitions = site_type_defs
        await self.db.flush()

        master_to_dag = {
            MASTER_MANUFACTURER: "PLANT",
            MASTER_INVENTORY: "DC",
            MASTER_VENDOR: "SUPPLIER",
            MASTER_CUSTOMER: "CUSTOMER",
            # Legacy aliases
            MASTER_MARKET_SUPPLY: "SUPPLIER",
            MASTER_MARKET_DEMAND: "CUSTOMER",
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

        # Create regional VENDOR and CUSTOMER sites from vendor/customer geography
        build_opts = opts or {}
        supply_regions, demand_regions = self._compute_market_regions(
            max_supply_regions=build_opts.get("max_supply_regions", 8),
            max_demand_regions=build_opts.get("max_demand_regions", 8),
            promotion_threshold=build_opts.get("region_promotion_threshold", 0.25),
        )

        # Create geography records for regional market sites
        region_geos = await self._create_region_geographies(
            {**supply_regions, **demand_regions}
        )

        for region_key, region_info in supply_regions.items():
            site_key = f"SUPPLY_{region_key}"
            supply_site = Site(
                config_id=self._config.id,
                name=site_key,
                type=region_info["label"],
                dag_type="SUPPLIER",
                master_type=MASTER_VENDOR,
                is_external=True,
                tpartner_type="vendor",
                geo_id=region_geos.get(region_key),
                attributes={
                    "region": region_key,
                    "countries": region_info["countries"],
                    "vendor_count": region_info["count"],
                },
            )
            self.db.add(supply_site)
            await self.db.flush()
            self._sites[site_key] = supply_site
            count += 1

        for region_key, region_info in demand_regions.items():
            site_key = f"DEMAND_{region_key}"
            demand_site = Site(
                config_id=self._config.id,
                name=site_key,
                type=region_info["label"],
                dag_type="CUSTOMER",
                master_type=MASTER_CUSTOMER,
                is_external=True,
                tpartner_type="customer",
                geo_id=region_geos.get(region_key),
                attributes={
                    "region": region_key,
                    "countries": region_info["countries"],
                    "customer_count": region_info["count"],
                },
            )
            self.db.add(demand_site)
            await self.db.flush()
            self._sites[site_key] = demand_site
            count += 1

        # Cache country → region_key lookups for use by _create_lanes
        self._supply_country_region: Dict[str, str] = {}
        for rk, info in supply_regions.items():
            for c in info["countries"]:
                self._supply_country_region[c] = rk
        self._demand_country_region: Dict[str, str] = {}
        for rk, info in demand_regions.items():
            for c in info["countries"]:
                self._demand_country_region[c] = rk

        logger.info(f"Created {count} sites ({len(supply_regions)} supply regions, {len(demand_regions)} demand regions)")
        return count

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
        """Create Product entities from MARA/MARC."""
        mara = self._data.get("MARA", pd.DataFrame())
        marc = self._data.get("MARC", pd.DataFrame())
        mvke = self._data.get("MVKE", pd.DataFrame())

        if mara.empty and marc.empty:
            logger.warning("No material data found")
            return 0

        # Get unique materials
        materials: Dict[str, Dict[str, Any]] = {}
        if not mara.empty and "MATNR" in mara.columns:
            for _, row in mara.iterrows():
                key = str(row["MATNR"]).strip()
                materials[key] = {
                    "name": str(row.get("MAKTX", key)).strip(),
                    "group": str(row.get("MATKL", "")).strip(),
                    "uom": str(row.get("MEINS", "EA")).strip(),
                    "type": str(row.get("MTART", "")).strip(),
                }

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
        created: Set[Tuple[int, int]] = set()

        # Determine which supply regions actually source to which plants
        eord = self._data.get("EORD", pd.DataFrame())
        ekpo = self._data.get("EKPO", pd.DataFrame())
        ekko = self._data.get("EKKO", pd.DataFrame())

        # plant → set of supply regions
        plant_supply_regions: Dict[str, Set[str]] = {}
        if not eord.empty and "LIFNR" in eord.columns and "WERKS" in eord.columns:
            for _, row in eord.iterrows():
                vid = str(row["LIFNR"]).strip()
                plant = str(row["WERKS"]).strip()
                region = vendor_region.get(vid)
                if region and plant in self._sites:
                    plant_supply_regions.setdefault(plant, set()).add(region)
        if not ekpo.empty and not ekko.empty:
            merged = ekpo.merge(
                ekko[["EBELN", "LIFNR"]].drop_duplicates(), on="EBELN", how="left",
            )
            if "LIFNR" in merged.columns and "WERKS" in merged.columns:
                for _, row in merged.iterrows():
                    vid = str(row["LIFNR"]).strip()
                    plant = str(row["WERKS"]).strip()
                    region = vendor_region.get(vid)
                    if region and plant in self._sites:
                        plant_supply_regions.setdefault(plant, set()).add(region)

        # Create inbound lanes: SUPPLY_{region} → plant
        for plant_key, regions in plant_supply_regions.items():
            plant_site = self._sites.get(plant_key)
            if not plant_site:
                continue
            for region in regions:
                supply_site = self._sites.get(f"SUPPLY_{region}")
                if supply_site and (supply_site.id, plant_site.id) not in created:
                    lt = avg_region_lt.get(region, 7)
                    lane = TransportationLane(
                        config_id=self._config.id,
                        from_site_id=supply_site.id,
                        to_site_id=plant_site.id,
                        capacity=10000,
                        lead_time_days={"min": max(1, lt - 2), "max": lt + 2},
                        supply_lead_time={"type": "deterministic", "value": lt},
                        demand_lead_time={"type": "deterministic", "value": 1},
                    )
                    self.db.add(lane)
                    created.add((supply_site.id, plant_site.id))
                    count += 1

        # Determine which demand regions each plant ships to
        likp = self._data.get("LIKP", pd.DataFrame())
        lips = self._data.get("LIPS", pd.DataFrame())
        vbap = self._data.get("VBAP", pd.DataFrame())

        plant_demand_regions: Dict[str, Set[str]] = {}
        if not lips.empty and not likp.empty:
            if "KUNNR" in likp.columns and "WERKS" in lips.columns:
                merged_del = lips.merge(
                    likp[["VBELN", "KUNNR"]].drop_duplicates(), on="VBELN", how="left",
                )
                if "KUNNR" in merged_del.columns:
                    for _, row in merged_del.iterrows():
                        cid = str(row["KUNNR"]).strip()
                        plant = str(row["WERKS"]).strip()
                        region = customer_region.get(cid)
                        if region and plant in self._sites:
                            plant_demand_regions.setdefault(plant, set()).add(region)
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
                        region = customer_region.get(cid)
                        if region and plant in self._sites:
                            plant_demand_regions.setdefault(plant, set()).add(region)

        # Create outbound lanes: plant → DEMAND_{region}
        for plant_key, regions in plant_demand_regions.items():
            plant_site = self._sites.get(plant_key)
            if not plant_site:
                continue
            for region in regions:
                demand_site = self._sites.get(f"DEMAND_{region}")
                if demand_site and (plant_site.id, demand_site.id) not in created:
                    lane = TransportationLane(
                        config_id=self._config.id,
                        from_site_id=plant_site.id,
                        to_site_id=demand_site.id,
                        capacity=10000,
                        lead_time_days={"min": 1, "max": 5},
                        supply_lead_time={"type": "deterministic", "value": 2},
                        demand_lead_time={"type": "deterministic", "value": 1},
                    )
                    self.db.add(lane)
                    created.add((plant_site.id, demand_site.id))
                    count += 1

        # Inter-plant transfers
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
                        if (src_site.id, dst_site.id) not in created:
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
                            created.add((src_site.id, dst_site.id))
                            count += 1

        await self.db.flush()
        logger.info(f"Created {count} transportation lanes")
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

        lfa1 = self._data.get("LFA1", pd.DataFrame())
        if not lfa1.empty and "LIFNR" in lfa1.columns:
            seen_vendors: Dict[str, dict] = {}
            for _, row in lfa1.iterrows():
                vendor_id = str(row["LIFNR"]).strip()
                if vendor_id and vendor_id not in seen_vendors:
                    seen_vendors[vendor_id] = {
                        "id": vendor_id,
                        "tpartner_type": "vendor",
                        "description": str(row.get("NAME1", vendor_id)).strip(),
                        "source": "SAP_LFA1",
                    }
            if seen_vendors:
                stmt = pg_insert(TradingPartner).values(list(seen_vendors.values()))
                stmt = stmt.on_conflict_do_update(
                    index_elements=["id"],
                    set_={"description": stmt.excluded.description, "source": stmt.excluded.source},
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
                    seen_customers[customer_id] = {
                        "id": customer_id,
                        "tpartner_type": "customer",
                        "description": str(row.get("NAME1", customer_id)).strip(),
                        "source": "SAP_KNA1",
                    }
            if seen_customers:
                stmt = pg_insert(TradingPartner).values(list(seen_customers.values()))
                stmt = stmt.on_conflict_do_update(
                    index_elements=["id"],
                    set_={"description": stmt.excluded.description, "source": stmt.excluded.source},
                )
                await self.db.execute(stmt)
                for cid in seen_customers:
                    self._trading_partners[cid] = cid
                customer_count = len(seen_customers)

        await self.db.flush()

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
        """Create ProductBom and ProductionProcess entities."""
        bom_count = 0
        prefix = f"CFG{self._config.id}_"

        # BOM from STPO (items) + STKO (headers)
        stpo = self._data.get("STPO", pd.DataFrame())
        stko = self._data.get("STKO", pd.DataFrame())

        if not stpo.empty and "STLNR" in stpo.columns:
            # Enrich with header base quantity
            base_qty_map = {}
            if not stko.empty and "STLNR" in stko.columns:
                for _, row in stko.iterrows():
                    bom_nr = str(row["STLNR"]).strip()
                    base_qty_map[bom_nr] = float(pd.to_numeric(row.get("BMENG", 1), errors="coerce") or 1)

            for _, row in stpo.iterrows():
                parent_mat = str(row.get("IDNRK", "")).strip()  # Component material
                bom_nr = str(row["STLNR"]).strip()

                if parent_mat and parent_mat in self._products:
                    base_qty = base_qty_map.get(bom_nr, 1.0)
                    comp_qty = float(pd.to_numeric(row.get("MENGE", 1), errors="coerce") or 1)
                    bom = ProductBom(
                        config_id=self._config.id,
                        product_id=f"{prefix}{parent_mat}",
                        component_product_id=f"{prefix}{str(row.get('IDNRK', '')).strip()}",
                        component_quantity=comp_qty / base_qty if base_qty else comp_qty,
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
        """Create InvLevel and InvPolicy from MARD data."""
        count = 0
        prefix = f"CFG{self._config.id}_"

        mard = self._data.get("MARD", pd.DataFrame())
        if mard.empty:
            return 0

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

            # Create default inventory policy
            policy = InvPolicy(
                config_id=self._config.id,
                product_id=product_id,
                site_id=site_id,
                ss_policy=default_policy,
                ss_days=safety_days,
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
        """Resolve SAP MATNR to our Product.id (with config prefix)."""
        mat_key = str(matnr).strip().lstrip("0") or "0"
        if mat_key in self._products:
            return self._products[mat_key].id
        # Try with leading-zero stripped key
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

        # Also try PIR forecasts if step 8 didn't find APO data
        if opts.get("include_pir_forecasts", True):
            pir_count = await self._create_pir_forecasts()
            if pir_count > 0:
                counts["pir_forecasts"] = pir_count

        return counts

    async def _create_outbound_orders(self, max_records: int = 5000) -> int:
        """Create OutboundOrderLine records from SAP sales orders (VBAK/VBAP)."""
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
            delivery_date = self._parse_sap_date(delivery_date_str) or order_date

            qty = float(pd.to_numeric(item.get("KWMENG", 0), errors="coerce") or 0)

            ob = OutboundOrderLine(
                order_id=f"SAP-SO-{vbeln}",
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
                # Use raw SQL because the SQLAlchemy model is out of sync with the DB schema
                await self.db.execute(
                    sql_text("""
                        INSERT INTO inbound_order_line
                            (order_id, line_number, product_id, to_site_id, order_type,
                             quantity_submitted, status, config_id, tenant_id)
                        VALUES (:order_id, :line_number, :product_id, :to_site_id, :order_type,
                                :quantity_submitted, :status, :config_id, :tenant_id)
                    """),
                    {
                        "order_id": f"SAP-PO-{ebeln}",
                        "line_number": int(pd.to_numeric(pi.get("EBELP", 1), errors="coerce") or 1),
                        "product_id": product_id,
                        "to_site_id": dest_site_id,
                        "order_type": "PURCHASE",
                        "quantity_submitted": qty,
                        "status": line_status,
                        "config_id": self._config.id,
                        "tenant_id": self.tenant_id,
                    },
                )

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

        count = 0
        for _, po in afko.iterrows():
            aufnr = str(po.get("AUFNR", "")).strip()
            plnbez = str(po.get("PLNBEZ", "")).strip()

            product_id = self._get_product_id(plnbez)
            if not product_id:
                continue

            # Find plant from AFPO or data
            site_id = None
            if not afpo.empty and "AUFNR" in afpo.columns:
                afpo_rows = afpo[afpo["AUFNR"].astype(str).str.strip() == aufnr]
                if not afpo_rows.empty:
                    werks = str(afpo_rows.iloc[0].get("DESSION", afpo_rows.iloc[0].get("WERKS", ""))).strip()
                    if werks:
                        site_id = self._get_site_id(werks)
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
            if not afpo.empty and "AUFNR" in afpo.columns:
                afpo_match = afpo[afpo["AUFNR"].astype(str).str.strip() == aufnr]
                if not afpo_match.empty:
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

    async def _create_pir_forecasts(self) -> int:
        """Create Forecast records from SAP Planned Independent Requirements (PBIM/PBED).

        Falls back to this when APO SNP data is not available.
        """
        pbim = self._data.get("PBIM", pd.DataFrame())
        pbed = self._data.get("PBED", pd.DataFrame())
        if pbed.empty:
            return 0

        # Build PIR header map: BDZEI → {MATNR, WERKS}
        header_map: Dict[str, pd.Series] = {}
        if not pbim.empty and "BDZEI" in pbim.columns:
            for _, row in pbim.iterrows():
                bdzei = str(row.get("BDZEI", "")).strip()
                if bdzei:
                    header_map[bdzei] = row

        count = 0
        for _, sched in pbed.iterrows():
            bdzei = str(sched.get("BDZEI", "")).strip()
            header = header_map.get(bdzei)
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
