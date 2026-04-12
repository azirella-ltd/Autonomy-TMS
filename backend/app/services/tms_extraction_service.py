"""
TMS Extraction Service — orchestrates data extraction from external TMS systems.

Sits between the API endpoints and the vendor-specific adapters. Handles:
- Adapter instantiation based on ERPConnection config
- Extraction orchestration (connect → extract → map → persist → disconnect)
- Result tracking and watermark management
- Error handling and retry logic

Usage:
    service = TMSExtractionService(db_session)
    result = await service.run_extraction(
        connection_id=1,
        entity_types=["shipments", "carriers"],
        mode="incremental",
    )
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.erp_connection import ERPConnection
from app.integrations.core.tms_adapter import (
    TMSExtractionAdapter,
    ExtractionMode,
    ExtractionResult,
    InjectionResult,
)

logger = logging.getLogger(__name__)


# ── Adapter Registry ────────────────────────────────────────────────────────
# Maps erp_type → adapter class. New vendors are added here.

def _get_adapter_class(erp_type: str):
    """Lazy-load adapter class by ERP type to avoid import-time deps."""
    adapters = {
        "sap": "app.integrations.sap.tms_extractor.SAPTMAdapter",
        "sap_s4hana": "app.integrations.sap.tms_extractor.SAPTMAdapter",
        "sap_tm": "app.integrations.sap.tms_extractor.SAPTMAdapter",
        # Future:
        # "oracle_otm": "app.integrations.oracle.tms_extractor.OracleTMAdapter",
        # "blue_yonder": "app.integrations.blue_yonder.tms_extractor.BlueYonderTMAdapter",
        # "manhattan": "app.integrations.manhattan.tms_extractor.ManhattanTMAdapter",
    }
    module_class = adapters.get(erp_type.lower())
    if not module_class:
        return None
    module_path, class_name = module_class.rsplit(".", 1)
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


class TMSExtractionService:
    """
    Orchestrates TMS data extraction from external systems.

    One instance per request/job. Stateless between calls (adapter
    is created per extraction run).
    """

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    # ── Run Extraction ───────────────────────────────────────────────────

    async def run_extraction(
        self,
        connection_id: int,
        tenant_id: int,
        entity_types: Optional[List[str]] = None,
        mode: str = "incremental",
        since: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Run a TMS extraction job against an ERP connection.

        Args:
            connection_id: ID of the ERPConnection record
            tenant_id: Tenant scope
            entity_types: Which entities to extract (default: all)
            mode: "full", "incremental", or "historical"
            since: For incremental — extract records changed since this time

        Returns:
            {"status": "completed", "results": [...ExtractionResult...], "duration_seconds": N}
        """
        start = datetime.utcnow()

        # 1. Load connection config
        connection = await self._get_connection(connection_id, tenant_id)
        if not connection:
            return {
                "status": "error",
                "error": f"Connection {connection_id} not found for tenant {tenant_id}",
            }

        # 2. Instantiate adapter
        adapter = self._create_adapter(connection)
        if not adapter:
            return {
                "status": "error",
                "error": f"No TMS adapter available for ERP type: {connection.erp_type}",
                "supported_types": ["sap", "sap_s4hana", "sap_tm"],
            }

        # 3. Connect
        try:
            connected = await adapter.connect()
            if not connected:
                return {"status": "error", "error": "Failed to connect to external TMS"}
        except Exception as e:
            logger.error(f"TMS extraction connection failed: {e}")
            return {"status": "error", "error": f"Connection error: {str(e)}"}

        # 4. Run extractions
        extraction_mode = ExtractionMode(mode) if mode in ExtractionMode.__members__.values() else ExtractionMode.INCREMENTAL
        types = entity_types or ["shipments", "loads", "carriers", "rates", "appointments", "exceptions"]
        results = []

        extractors = {
            "shipments": lambda: adapter.extract_shipments(since=since, mode=extraction_mode),
            "loads": lambda: adapter.extract_loads(since=since, mode=extraction_mode),
            "carriers": lambda: adapter.extract_carriers(mode=extraction_mode),
            "rates": lambda: adapter.extract_rates(mode=extraction_mode),
            "appointments": lambda: adapter.extract_appointments(since=since, mode=extraction_mode),
            "exceptions": lambda: adapter.extract_exceptions(since=since, mode=extraction_mode),
        }

        for entity_type in types:
            if entity_type in extractors:
                try:
                    result = await extractors[entity_type]()
                    results.append({
                        "entity_type": result.entity_type,
                        "records_extracted": result.records_extracted,
                        "records_mapped": result.records_mapped,
                        "records_skipped": result.records_skipped,
                        "errors": result.errors,
                        "duration_seconds": result.duration_seconds,
                        "watermark": result.watermark,
                    })
                    logger.info(
                        f"TMS extraction [{entity_type}]: "
                        f"{result.records_extracted} extracted, "
                        f"{result.records_mapped} mapped"
                    )
                except Exception as e:
                    logger.error(f"TMS extraction [{entity_type}] failed: {e}")
                    results.append({
                        "entity_type": entity_type,
                        "records_extracted": 0,
                        "records_mapped": 0,
                        "records_skipped": 0,
                        "errors": [{"error": str(e)}],
                        "duration_seconds": 0,
                    })

        # 5. Disconnect
        try:
            await adapter.disconnect()
        except Exception as e:
            logger.warning(f"TMS adapter disconnect error: {e}")

        duration = (datetime.utcnow() - start).total_seconds()

        return {
            "status": "completed",
            "connection_id": connection_id,
            "erp_type": connection.erp_type,
            "mode": mode,
            "entity_types": types,
            "results": results,
            "duration_seconds": duration,
            "completed_at": datetime.utcnow().isoformat(),
        }

    # ── Test Connection ──────────────────────────────────────────────────

    async def test_connection(
        self, connection_id: int, tenant_id: int
    ) -> Dict[str, Any]:
        """Test a TMS-compatible ERP connection."""
        connection = await self._get_connection(connection_id, tenant_id)
        if not connection:
            return {"connected": False, "error": "Connection not found"}

        adapter = self._create_adapter(connection)
        if not adapter:
            return {
                "connected": False,
                "error": f"No TMS adapter for ERP type: {connection.erp_type}",
            }

        try:
            result = await adapter.test_connection()
            return result
        except Exception as e:
            return {"connected": False, "error": str(e)}
        finally:
            try:
                await adapter.disconnect()
            except Exception:
                pass

    # ── Inject Decision ──────────────────────────────────────────────────

    async def inject_decision(
        self,
        connection_id: int,
        tenant_id: int,
        decision: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Push an AIIO-governed decision back to the external TMS.

        Called by the decision governance pipeline when a decision is
        ACTIONED (AUTOMATE/INFORM mode) or approved by a human (INSPECT mode).
        """
        connection = await self._get_connection(connection_id, tenant_id)
        if not connection:
            return {"success": False, "error": "Connection not found"}

        adapter = self._create_adapter(connection)
        if not adapter:
            return {"success": False, "error": f"No adapter for: {connection.erp_type}"}

        try:
            connected = await adapter.connect()
            if not connected:
                return {"success": False, "error": "Connection failed"}

            result = await adapter.inject_decision(decision)
            return {
                "success": result.success,
                "decision_id": result.decision_id,
                "decision_type": result.decision_type,
                "external_id": result.external_id,
                "error": result.error,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            try:
                await adapter.disconnect()
            except Exception:
                pass

    # ── Private Helpers ──────────────────────────────────────────────────

    async def _get_connection(
        self, connection_id: int, tenant_id: int
    ) -> Optional[ERPConnection]:
        """Load ERPConnection by ID with tenant scoping."""
        stmt = select(ERPConnection).where(
            ERPConnection.id == connection_id,
            ERPConnection.tenant_id == tenant_id,
            ERPConnection.is_active == True,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def _create_adapter(self, connection: ERPConnection) -> Optional[TMSExtractionAdapter]:
        """Instantiate the appropriate adapter for this connection's ERP type."""
        adapter_class = _get_adapter_class(connection.erp_type)
        if not adapter_class:
            return None

        # Build connection config from ERPConnection model
        from app.integrations.sap.tms_extractor import SAPTMConnectionConfig

        params = connection.connection_params or {}

        if connection.erp_type.lower() in ("sap", "sap_s4hana", "sap_tm"):
            config = SAPTMConnectionConfig(
                tenant_id=connection.tenant_id,
                connection_name=connection.name,
                base_url=connection.base_url,
                environment="production" if connection.is_validated else "sandbox",
                ashost=params.get("ashost"),
                sysnr=params.get("sysnr", "00"),
                client=params.get("client", "100"),
                sap_user=params.get("user"),
                sap_password=params.get("password"),  # In prod: decrypt from auth_credentials_encrypted
                odata_base_url=connection.base_url,
                odata_client_id=params.get("odata_client_id"),
                odata_client_secret=params.get("odata_client_secret"),
                preferred_method=connection.connection_method or "odata",
                company_code=params.get("company_code"),
                plant_filter=params.get("plant_filter"),
                shipping_type_filter=params.get("shipping_type_filter"),
            )
            return adapter_class(config)

        # Generic fallback for future adapters
        from app.integrations.core.tms_adapter import ConnectionConfig
        config = ConnectionConfig(
            tenant_id=connection.tenant_id,
            connection_name=connection.name,
            base_url=connection.base_url,
        )
        return adapter_class(config)
