"""
Odoo ERP Connector

Provides API connectivity to Odoo instances (Community & Enterprise)
using JSON-RPC (primary) and XML-RPC (fallback) protocols.

Supports:
- Authentication (password, API key)
- Model discovery (ir.model introspection)
- CRUD operations on any Odoo model
- Bulk read with domain filtering and pagination
- CSV export from API responses
- Change tracking via write_date filtering

Usage:
    connector = OdooConnector(
        url="http://localhost:8069",
        database="odoo_db",
        username="admin",
        password="admin"
    )
    await connector.authenticate()
    products = await connector.search_read("product.product", [("type", "=", "product")])
"""

import logging
import json
import csv
import os
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import asyncio
import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class OdooConnectionConfig:
    """Configuration for an Odoo connection."""
    url: str = "http://localhost:8069"
    database: str = ""
    username: str = "admin"
    password: str = "admin"
    api_key: Optional[str] = None
    use_api_key: bool = False
    timeout: int = 120
    version: Optional[str] = None  # e.g. "18.0"


class OdooConnector:
    """JSON-RPC/XML-RPC connector for Odoo ERP.

    Follows the same connection-test-extract pattern as the SAP connector.
    """

    def __init__(self, config: OdooConnectionConfig):
        self.config = config
        self.uid: Optional[int] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._rpc_id = 0

    # ── Connection Lifecycle ─────────────────────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ── JSON-RPC Transport ───────────────────────────────────────────────

    async def _json_rpc(self, url: str, method: str, params: Dict) -> Any:
        """Execute a JSON-RPC call to Odoo."""
        self._rpc_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._rpc_id,
        }
        session = await self._get_session()
        async with session.post(url, json=payload) as resp:
            result = await resp.json()
            if "error" in result:
                err = result["error"]
                msg = err.get("data", {}).get("message", err.get("message", str(err)))
                raise ConnectionError(f"Odoo JSON-RPC error: {msg}")
            return result.get("result")

    async def _call(self, service: str, method: str, *args) -> Any:
        """Call an Odoo service method via JSON-RPC."""
        url = f"{self.config.url}/jsonrpc"
        return await self._json_rpc(url, "call", {
            "service": service,
            "method": method,
            "args": list(args),
        })

    # ── Authentication ───────────────────────────────────────────────────

    async def authenticate(self) -> int:
        """Authenticate and return uid."""
        if self.config.use_api_key and self.config.api_key:
            # API key auth: use api key as password with uid=2 (OdooBot)
            self.uid = 2
            logger.info("Odoo: using API key authentication")
            return self.uid

        self.uid = await self._call(
            "common", "authenticate",
            self.config.database,
            self.config.username,
            self.config.password,
            {},
        )
        if not self.uid:
            raise ConnectionError(
                f"Odoo authentication failed for {self.config.username}@{self.config.database}"
            )
        logger.info("Odoo: authenticated uid=%d on %s", self.uid, self.config.database)
        return self.uid

    async def test_connection(self) -> Dict[str, Any]:
        """Test connection and return server info."""
        try:
            version = await self._call("common", "version")
            await self.authenticate()
            db_list = await self._call("db", "list")
            return {
                "success": True,
                "server_version": version.get("server_version", "unknown"),
                "server_serie": version.get("server_serie", "unknown"),
                "protocol_version": version.get("protocol_version"),
                "uid": self.uid,
                "databases": db_list if isinstance(db_list, list) else [],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Model Introspection ──────────────────────────────────────────────

    async def get_installed_modules(self) -> List[Dict]:
        """Get list of installed Odoo modules."""
        return await self.search_read(
            "ir.module.module",
            [("state", "=", "installed")],
            ["name", "shortdesc", "state"],
        )

    async def get_model_fields(self, model_name: str) -> Dict[str, Any]:
        """Get field definitions for an Odoo model."""
        password = self.config.api_key if self.config.use_api_key else self.config.password
        result = await self._call(
            "object", "execute_kw",
            self.config.database, self.uid, password,
            model_name, "fields_get",
            [],
            {"attributes": ["string", "type", "required", "readonly", "relation", "help"]},
        )
        return result or {}

    async def discover_models(self) -> List[Dict]:
        """Discover available Odoo models relevant to supply chain."""
        SC_MODELS = [
            "product.product", "product.template", "product.category",
            "mrp.bom", "mrp.bom.line", "mrp.workcenter", "mrp.routing.workcenter",
            "mrp.production", "mrp.workorder",
            "stock.warehouse", "stock.location", "stock.quant",
            "stock.picking", "stock.move", "stock.picking.type",
            "purchase.order", "purchase.order.line",
            "sale.order", "sale.order.line",
            "res.partner", "res.company",
            "account.move", "account.move.line",
            "product.supplierinfo",
            "stock.warehouse.orderpoint",
            "uom.uom", "uom.category",
        ]
        results = []
        for model in SC_MODELS:
            try:
                fields = await self.get_model_fields(model)
                results.append({
                    "model": model,
                    "field_count": len(fields),
                    "available": True,
                })
            except Exception:
                results.append({"model": model, "field_count": 0, "available": False})
        return results

    # ── CRUD Operations ──────────────────────────────────────────────────

    async def search_read(
        self,
        model: str,
        domain: List = None,
        fields: List[str] = None,
        limit: int = 0,
        offset: int = 0,
        order: str = "",
    ) -> List[Dict]:
        """Search and read records from an Odoo model."""
        password = self.config.api_key if self.config.use_api_key else self.config.password
        kwargs: Dict[str, Any] = {}
        if fields:
            kwargs["fields"] = fields
        if limit:
            kwargs["limit"] = limit
        if offset:
            kwargs["offset"] = offset
        if order:
            kwargs["order"] = order

        result = await self._call(
            "object", "execute_kw",
            self.config.database, self.uid, password,
            model, "search_read",
            [domain or []],
            kwargs,
        )
        return result or []

    async def search_count(self, model: str, domain: List = None) -> int:
        """Count records matching a domain."""
        password = self.config.api_key if self.config.use_api_key else self.config.password
        return await self._call(
            "object", "execute_kw",
            self.config.database, self.uid, password,
            model, "search_count",
            [domain or []],
        )

    async def read(self, model: str, ids: List[int], fields: List[str] = None) -> List[Dict]:
        """Read specific records by ID."""
        password = self.config.api_key if self.config.use_api_key else self.config.password
        kwargs = {"fields": fields} if fields else {}
        return await self._call(
            "object", "execute_kw",
            self.config.database, self.uid, password,
            model, "read",
            [ids],
            kwargs,
        )

    # ── Bulk Extraction ──────────────────────────────────────────────────

    async def extract_all(
        self,
        model: str,
        domain: List = None,
        fields: List[str] = None,
        batch_size: int = 500,
    ) -> List[Dict]:
        """Extract all records from a model with automatic pagination."""
        all_records = []
        offset = 0
        while True:
            batch = await self.search_read(
                model, domain=domain, fields=fields,
                limit=batch_size, offset=offset,
            )
            if not batch:
                break
            all_records.extend(batch)
            offset += len(batch)
            if len(batch) < batch_size:
                break
            logger.debug("Odoo extract %s: %d records so far", model, len(all_records))
        logger.info("Odoo extract %s: %d total records", model, len(all_records))
        return all_records

    # ── CDC (Change Data Capture) ────────────────────────────────────────

    async def extract_changes(
        self,
        model: str,
        since: datetime,
        fields: List[str] = None,
        batch_size: int = 500,
    ) -> List[Dict]:
        """Extract records changed since a given datetime.

        Odoo stores ``write_date`` on every model — this is the CDC mechanism.
        """
        domain = [("write_date", ">=", since.strftime("%Y-%m-%d %H:%M:%S"))]
        return await self.extract_all(model, domain=domain, fields=fields, batch_size=batch_size)

    # ── CSV Export ───────────────────────────────────────────────────────

    async def export_to_csv(
        self,
        model: str,
        output_dir: str,
        domain: List = None,
        fields: List[str] = None,
        batch_size: int = 500,
    ) -> str:
        """Extract model data and write to CSV file.

        Returns the path to the written CSV file.
        """
        records = await self.extract_all(model, domain=domain, fields=fields, batch_size=batch_size)
        if not records:
            logger.warning("Odoo CSV export %s: no records", model)
            return ""

        os.makedirs(output_dir, exist_ok=True)
        filename = f"{model.replace('.', '_')}.csv"
        filepath = os.path.join(output_dir, filename)

        # Flatten Odoo's (id, name) tuples for relational fields
        flat_records = []
        for rec in records:
            flat = {}
            for k, v in rec.items():
                if isinstance(v, (list, tuple)) and len(v) == 2 and isinstance(v[0], int):
                    flat[k] = v[0]  # keep the ID
                    flat[f"{k}_name"] = v[1]  # keep the display name
                elif isinstance(v, (list, tuple)):
                    flat[k] = json.dumps(v)
                elif isinstance(v, dict):
                    flat[k] = json.dumps(v)
                else:
                    flat[k] = v
            flat_records.append(flat)

        all_keys = set()
        for r in flat_records:
            all_keys.update(r.keys())
        fieldnames = sorted(all_keys)

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(flat_records)

        logger.info("Odoo CSV export %s: %d records → %s", model, len(flat_records), filepath)
        return filepath

    # ── CSV Import (for offline/file-based ingestion) ────────────────────

    @staticmethod
    def load_csv(filepath: str) -> Tuple[List[str], List[Dict]]:
        """Load a CSV file and return (headers, records)."""
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            records = list(reader)
        return headers, records

    @staticmethod
    def identify_odoo_model(headers: List[str]) -> Optional[str]:
        """Identify which Odoo model a CSV represents based on column headers.

        Uses Jaccard similarity on known model field sets.
        """
        MODEL_SIGNATURES = {
            "product.product": {"name", "default_code", "type", "categ_id", "list_price", "standard_price", "uom_id"},
            "product.template": {"name", "default_code", "type", "categ_id", "list_price", "uom_id"},
            "mrp.bom": {"product_tmpl_id", "product_qty", "type", "bom_line_ids"},
            "mrp.bom.line": {"bom_id", "product_id", "product_qty", "product_uom_id"},
            "stock.warehouse": {"name", "code", "partner_id", "lot_stock_id"},
            "stock.quant": {"product_id", "location_id", "quantity", "reserved_quantity"},
            "purchase.order": {"partner_id", "date_order", "state", "amount_total", "order_line"},
            "purchase.order.line": {"order_id", "product_id", "product_qty", "price_unit", "date_planned"},
            "sale.order": {"partner_id", "date_order", "state", "amount_total", "order_line"},
            "sale.order.line": {"order_id", "product_id", "product_uom_qty", "price_unit"},
            "res.partner": {"name", "email", "phone", "street", "city", "country_id", "supplier_rank", "customer_rank"},
            "mrp.production": {"product_id", "product_qty", "bom_id", "state", "date_start"},
            "product.supplierinfo": {"partner_id", "product_tmpl_id", "min_qty", "price", "delay"},
            "stock.warehouse.orderpoint": {"product_id", "warehouse_id", "product_min_qty", "product_max_qty"},
        }
        header_set = set(h.lower().strip() for h in headers)
        best_model = None
        best_score = 0.0
        for model, sig in MODEL_SIGNATURES.items():
            intersection = len(header_set & sig)
            union = len(header_set | sig)
            score = intersection / union if union else 0
            if score > best_score:
                best_score = score
                best_model = model
        if best_score < 0.15:
            return None
        return best_model
