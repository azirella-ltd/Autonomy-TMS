"""
Odoo Data Extraction Service

Orchestrates master data, transaction data, and CDC extraction from Odoo.
Follows the same 3-phase pipeline as SAP ingestion:
    Phase 1: Master Data — sites, products, BOMs, vendors, customers, inventory
    Phase 2: CDC — change detection via write_date filtering
    Phase 3: Transaction Data — POs, SOs, production orders, shipments

Extracted data is mapped to AWS SC entities and written to the Autonomy DB.
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class ExtractionPhase(str, Enum):
    MASTER_DATA = "master_data"
    CDC = "cdc"
    TRANSACTION = "transaction"


# ── Models grouped by extraction phase ───────────────────────────────────────

MASTER_DATA_MODELS = {
    # Tier 0: Organisation
    "res.company": ["id", "name", "country_id", "currency_id", "street", "city", "zip", "phone", "vat"],
    # Tier 1: Sites
    "stock.warehouse": ["id", "name", "code", "partner_id", "company_id", "active"],
    "stock.location": ["id", "name", "complete_name", "usage", "location_id", "warehouse_id", "company_id", "active"],
    # Tier 2: Products
    "product.product": [
        "id", "name", "default_code", "type", "categ_id", "uom_id",
        "list_price", "standard_price", "weight", "volume", "barcode",
        "active", "create_date", "write_date",
        # APS heuristic parameters for digital twin
        "produce_delay", "sale_delay", "route_ids",
        "sale_ok", "purchase_ok",
    ],
    "product.category": ["id", "name", "complete_name", "parent_id"],
    # Tier 3: Trading partners (vendors & customers)
    "res.partner": [
        "id", "name", "country_id", "state_id", "city", "zip", "street",
        "phone", "email", "supplier_rank", "customer_rank", "company_type",
        "is_company", "active",
    ],
    # Tier 4: Vendor-product sourcing
    "product.supplierinfo": [
        "id", "partner_id", "product_tmpl_id", "product_id",
        "min_qty", "price", "delay", "currency_id",
        "date_start", "date_end", "company_id",
    ],
    # Tier 5: BOMs & work centers
    "mrp.bom": [
        "id", "product_tmpl_id", "product_id", "product_qty", "product_uom_id",
        "type", "code", "active", "company_id",
    ],
    "mrp.bom.line": [
        "id", "bom_id", "product_id", "product_qty", "product_uom_id",
    ],
    "mrp.workcenter": [
        "id", "name", "capacity", "time_efficiency", "oee_target",
        "costs_hour", "company_id", "active",
    ],
    # Tier 6: Inventory levels & policies
    "stock.quant": [
        "id", "product_id", "location_id", "quantity", "reserved_quantity",
        "company_id", "write_date",
    ],
    "stock.warehouse.orderpoint": [
        "id", "product_id", "warehouse_id", "location_id",
        "product_min_qty", "product_max_qty", "qty_multiple",
        "trigger", "route_id", "group_id",
        "company_id", "active",
    ],
}

TRANSACTION_MODELS = {
    # Purchase orders
    "purchase.order": [
        "id", "name", "partner_id", "date_order", "date_planned",
        "state", "amount_total", "currency_id", "company_id",
    ],
    "purchase.order.line": [
        "id", "order_id", "product_id", "product_qty", "qty_received",
        "price_unit", "date_planned",
    ],
    # Sales orders
    "sale.order": [
        "id", "name", "partner_id", "date_order", "commitment_date",
        "state", "amount_total", "currency_id", "company_id", "warehouse_id",
    ],
    "sale.order.line": [
        "id", "order_id", "product_id", "product_uom_qty", "qty_delivered",
        "price_unit",
    ],
    # Manufacturing orders
    "mrp.production": [
        "id", "name", "product_id", "product_qty", "qty_produced",
        "bom_id", "state", "date_start", "date_finished", "company_id",
    ],
    # Stock transfers
    "stock.picking": [
        "id", "name", "origin", "partner_id", "picking_type_id",
        "location_id", "location_dest_id", "state",
        "scheduled_date", "date_done", "company_id",
    ],
    "stock.move": [
        "id", "picking_id", "product_id", "product_uom_qty", "quantity",
        "location_id", "location_dest_id", "state",
    ],
}


@dataclass
class ExtractionResult:
    """Result of extracting data from a single Odoo model."""
    model: str
    phase: ExtractionPhase
    record_count: int = 0
    success: bool = True
    error: Optional[str] = None
    duration_ms: int = 0
    csv_path: Optional[str] = None

    def to_dict(self):
        return {
            "model": self.model,
            "phase": self.phase.value,
            "record_count": self.record_count,
            "success": self.success,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "csv_path": self.csv_path,
        }


@dataclass
class ExtractionJobResult:
    """Aggregate result for a full extraction job."""
    phase: ExtractionPhase
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    model_results: List[ExtractionResult] = field(default_factory=list)
    total_records: int = 0
    success: bool = True

    def to_dict(self):
        return {
            "phase": self.phase.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "model_results": [r.to_dict() for r in self.model_results],
            "total_records": self.total_records,
            "success": self.success,
            "models_extracted": len([r for r in self.model_results if r.success]),
            "models_failed": len([r for r in self.model_results if not r.success]),
        }


class OdooExtractionService:
    """Orchestrates data extraction from Odoo.

    Usage:
        connector = OdooConnector(config)
        await connector.authenticate()
        service = OdooExtractionService(connector)
        result = await service.extract_master_data(output_dir="/tmp/odoo_extract")
    """

    def __init__(self, connector):
        """
        Args:
            connector: An authenticated OdooConnector instance.
        """
        self.connector = connector

    async def extract_master_data(
        self,
        output_dir: Optional[str] = None,
        models: Optional[List[str]] = None,
    ) -> ExtractionJobResult:
        """Phase 1: Extract all master data from Odoo.

        Args:
            output_dir: If provided, also write CSV files for each model.
            models: Subset of models to extract. Default: all master data models.
        """
        job = ExtractionJobResult(phase=ExtractionPhase.MASTER_DATA)
        target_models = models or list(MASTER_DATA_MODELS.keys())

        for model in target_models:
            fields = MASTER_DATA_MODELS.get(model)
            if not fields:
                continue
            result = await self._extract_model(model, fields, ExtractionPhase.MASTER_DATA, output_dir)
            job.model_results.append(result)
            job.total_records += result.record_count
            if not result.success:
                job.success = False

        job.completed_at = datetime.utcnow()
        logger.info(
            "Odoo master data extraction: %d models, %d records, success=%s",
            len(job.model_results), job.total_records, job.success,
        )
        return job

    async def extract_transaction_data(
        self,
        output_dir: Optional[str] = None,
        models: Optional[List[str]] = None,
    ) -> ExtractionJobResult:
        """Phase 3: Extract transaction data from Odoo."""
        job = ExtractionJobResult(phase=ExtractionPhase.TRANSACTION)
        target_models = models or list(TRANSACTION_MODELS.keys())

        for model in target_models:
            fields = TRANSACTION_MODELS.get(model)
            if not fields:
                continue
            result = await self._extract_model(model, fields, ExtractionPhase.TRANSACTION, output_dir)
            job.model_results.append(result)
            job.total_records += result.record_count
            if not result.success:
                job.success = False

        job.completed_at = datetime.utcnow()
        return job

    async def extract_changes(
        self,
        since: datetime,
        output_dir: Optional[str] = None,
    ) -> ExtractionJobResult:
        """Phase 2: CDC — extract records changed since last sync.

        Odoo uses write_date as the CDC mechanism.
        """
        job = ExtractionJobResult(phase=ExtractionPhase.CDC)

        # CDC applies to all master + transaction models
        all_models = {**MASTER_DATA_MODELS, **TRANSACTION_MODELS}
        for model, fields in all_models.items():
            start = datetime.utcnow()
            try:
                records = await self.connector.extract_changes(model, since, fields=fields)
                duration = int((datetime.utcnow() - start).total_seconds() * 1000)

                csv_path = None
                if output_dir and records:
                    csv_path = await self.connector.export_to_csv(
                        model, output_dir,
                        domain=[("write_date", ">=", since.strftime("%Y-%m-%d %H:%M:%S"))],
                        fields=fields,
                    )

                result = ExtractionResult(
                    model=model,
                    phase=ExtractionPhase.CDC,
                    record_count=len(records),
                    duration_ms=duration,
                    csv_path=csv_path,
                )
            except Exception as e:
                duration = int((datetime.utcnow() - start).total_seconds() * 1000)
                result = ExtractionResult(
                    model=model,
                    phase=ExtractionPhase.CDC,
                    success=False,
                    error=str(e),
                    duration_ms=duration,
                )

            job.model_results.append(result)
            job.total_records += result.record_count
            if not result.success:
                job.success = False

        job.completed_at = datetime.utcnow()
        changed_models = [r for r in job.model_results if r.record_count > 0]
        logger.info(
            "Odoo CDC extraction (since %s): %d models changed, %d total records",
            since.isoformat(), len(changed_models), job.total_records,
        )
        return job

    # ── Internal ─────────────────────────────────────────────────────────

    async def _extract_model(
        self,
        model: str,
        fields: List[str],
        phase: ExtractionPhase,
        output_dir: Optional[str] = None,
    ) -> ExtractionResult:
        """Extract a single Odoo model."""
        start = datetime.utcnow()
        try:
            # Only extract storable products (type='product'), not services/consumables
            domain = []
            if model == "product.product":
                domain = [("type", "=", "product")]
            elif model == "stock.quant":
                # Only internal locations (actual inventory)
                domain = [("location_id.usage", "=", "internal")]
            elif model == "res.partner":
                # Only companies (skip individual contacts)
                domain = [("is_company", "=", True)]
            elif model == "stock.location":
                # Only internal locations
                domain = [("usage", "=", "internal")]

            records = await self.connector.extract_all(model, domain=domain, fields=fields)
            duration = int((datetime.utcnow() - start).total_seconds() * 1000)

            csv_path = None
            if output_dir and records:
                csv_path = await self.connector.export_to_csv(
                    model, output_dir, domain=domain, fields=fields,
                )

            return ExtractionResult(
                model=model,
                phase=phase,
                record_count=len(records),
                duration_ms=duration,
                csv_path=csv_path,
            )
        except Exception as e:
            duration = int((datetime.utcnow() - start).total_seconds() * 1000)
            logger.warning("Odoo extract %s failed: %s", model, e)
            return ExtractionResult(
                model=model,
                phase=phase,
                success=False,
                error=str(e),
                duration_ms=duration,
            )
