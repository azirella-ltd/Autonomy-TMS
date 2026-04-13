"""
Oracle OTM (Transportation Management) Extraction Adapter — SKELETON.

Oracle OTM is REST-native (OTM 6.4+), so this adapter is far thinner
than the SAP TM one — no RFC/BAPI complexity. The API surface we need:

    GET  /GC3/glog.webserver.util.RestServlet?action=find
         &resource=SHIPMENT&query=...
    POST /GC3/glog.webserver.util.RestServlet?action=save
         &resource=SHIPMENT

Basic auth with domain-qualified user: `DEFAULT/{user}`.

OTM entities and their TMS mappings:

| OTM resource       | TMS entity           | Notes                           |
|--------------------|----------------------|---------------------------------|
| SHIPMENT           | Shipment + Load      | OTM's shipment = SAP freight order |
| ORDER_RELEASE      | Shipment (pre-plan)  | Unplanned demand unit           |
| SERVPROV           | Carrier              | Service provider master         |
| RATE_OFFERING      | FreightRate          | Tariff + lane config            |
| LOCATION           | Site / Facility      | Already modeled in AWS SC DM    |
| ORDER_MOVEMENT     | ShipmentLeg          | Multi-leg movement              |
| SHIPMENT_STATUS    | TrackingEvent        | In-transit milestones           |

This file implements the connection + structural skeleton. Mapping
bodies are intentionally minimal — flesh out per-customer during the
Oracle OTM engagement (ERP-5 follow-up work).

See docs/TMS_ERP_INTEGRATION.md § "Oracle OTM-specific data mapping".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.tms_adapter import (
    ConnectionConfig,
    ExtractionMode,
    ExtractionResult,
    InjectionResult,
    TMSExtractionAdapter,
)

logger = logging.getLogger(__name__)


@dataclass
class OracleOTMConnectionConfig(ConnectionConfig):
    """Oracle OTM REST connection configuration."""
    base_url: Optional[str] = None          # e.g. https://otmgtm.oracle.com
    domain: str = "DEFAULT"
    otm_user: Optional[str] = None
    otm_password: Optional[str] = None
    # Filters
    domain_filter: Optional[List[str]] = None   # OTM domain list
    servprov_filter: Optional[List[str]] = None  # Restrict carriers
    verify_ssl: bool = True


class OracleOTMAdapter(TMSExtractionAdapter):
    """
    Oracle OTM extraction/injection adapter — skeleton.

    Implements the TMSExtractionAdapter contract against Oracle OTM's
    REST web services. All methods connect/authenticate cleanly; mapping
    bodies are minimal and expected to be fleshed out when the first
    Oracle OTM customer comes onboard.
    """

    def __init__(self, config: OracleOTMConnectionConfig):
        super().__init__(config)
        self.config: OracleOTMConnectionConfig = config
        self._client = None  # httpx.AsyncClient

    # ── Connection ──────────────────────────────────────────────────

    async def connect(self) -> bool:
        try:
            import httpx
            if not self.config.base_url:
                logger.error("Oracle OTM base_url not configured")
                self._connected = False
                return False
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                auth=(
                    f"{self.config.domain}/{self.config.otm_user or ''}",
                    self.config.otm_password or "",
                ),
                verify=self.config.verify_ssl,
                timeout=120.0,
                headers={"Accept": "application/json"},
            )
            # Probe with a cheap request — `find` on DOMAIN resource.
            resp = await self._client.get(
                "/GC3/glog.webserver.util.RestServlet",
                params={"action": "find", "resource": "DOMAIN", "maxResults": 1},
            )
            self._connected = resp.status_code < 400
            if not self._connected:
                logger.error(
                    "Oracle OTM probe failed: HTTP %s %s",
                    resp.status_code, resp.text[:200],
                )
            return self._connected
        except Exception as e:
            logger.error("Oracle OTM connect failed: %s", e)
            self._connected = False
            return False

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None
        self._connected = False

    async def test_connection(self) -> Dict[str, Any]:
        if not self._connected:
            ok = await self.connect()
            if not ok:
                return {"connected": False, "message": "Oracle OTM probe failed"}
        return {"connected": True, "base_url": self.config.base_url}

    # ── Private REST helper ─────────────────────────────────────────

    async def _find(
        self,
        resource: str,
        query: Optional[Dict[str, str]] = None,
        max_results: int = 0,
    ) -> List[Dict[str, Any]]:
        """Issue a `find` against an OTM resource. Returns list of dicts."""
        if not self._client:
            return []
        params: Dict[str, Any] = {"action": "find", "resource": resource}
        if query:
            params.update({f"query.{k}": v for k, v in query.items()})
        if max_results:
            params["maxResults"] = str(max_results)
        try:
            resp = await self._client.get(
                "/GC3/glog.webserver.util.RestServlet", params=params,
            )
            if resp.status_code != 200:
                logger.warning(
                    "Oracle OTM find %s HTTP %s", resource, resp.status_code,
                )
                return []
            data = resp.json()
            return data.get(resource, []) if isinstance(data, dict) else []
        except Exception as e:
            logger.error("Oracle OTM find %s failed: %s", resource, e)
            return []

    # ── Extraction ──────────────────────────────────────────────────

    async def extract_shipments(
        self,
        since: Optional[datetime] = None,
        mode: ExtractionMode = ExtractionMode.INCREMENTAL,
        batch_size: int = 500,
    ) -> ExtractionResult:
        start = datetime.utcnow()
        query: Dict[str, str] = {}
        if since and mode == ExtractionMode.INCREMENTAL:
            query["update_date__ge"] = since.isoformat()
        raw = await self._find("SHIPMENT", query, max_results=batch_size)
        records = [self._map_shipment(r) for r in raw]
        return ExtractionResult(
            entity_type="shipments",
            records_extracted=len(records),
            records_mapped=len(records),
            records_skipped=0,
            errors=[],
            duration_seconds=(datetime.utcnow() - start).total_seconds(),
        )

    async def extract_loads(
        self,
        since: Optional[datetime] = None,
        mode: ExtractionMode = ExtractionMode.INCREMENTAL,
        batch_size: int = 500,
    ) -> ExtractionResult:
        # In OTM, loads are the same SHIPMENT resource; ORDER_MOVEMENT
        # holds the leg detail. We surface legs here.
        raw = await self._find("ORDER_MOVEMENT", max_results=batch_size)
        records = [self._map_order_movement(r) for r in raw]
        return ExtractionResult(
            entity_type="loads",
            records_extracted=len(records),
            records_mapped=len(records),
            records_skipped=0,
            errors=[],
        )

    async def extract_carriers(
        self, mode: ExtractionMode = ExtractionMode.FULL,
    ) -> ExtractionResult:
        raw = await self._find("SERVPROV")
        records = [self._map_servprov(r) for r in raw]
        return ExtractionResult(
            entity_type="carriers",
            records_extracted=len(records),
            records_mapped=len(records),
            records_skipped=0,
            errors=[],
        )

    async def extract_rates(
        self, mode: ExtractionMode = ExtractionMode.FULL,
    ) -> ExtractionResult:
        raw = await self._find("RATE_OFFERING")
        records = [self._map_rate_offering(r) for r in raw]
        return ExtractionResult(
            entity_type="rates",
            records_extracted=len(records),
            records_mapped=len(records),
            records_skipped=0,
            errors=[],
        )

    async def extract_appointments(
        self,
        since: Optional[datetime] = None,
        mode: ExtractionMode = ExtractionMode.INCREMENTAL,
    ) -> ExtractionResult:
        # OTM models appointments as SHIPMENT_STOP records with scheduled
        # start/end. We surface them separately here.
        raw = await self._find("SHIPMENT_STOP")
        records = [self._map_shipment_stop(r) for r in raw]
        return ExtractionResult(
            entity_type="appointments",
            records_extracted=len(records),
            records_mapped=len(records),
            records_skipped=0,
            errors=[],
        )

    async def extract_exceptions(
        self,
        since: Optional[datetime] = None,
        mode: ExtractionMode = ExtractionMode.INCREMENTAL,
    ) -> ExtractionResult:
        # OTM surfaces exceptions via SHIPMENT_STATUS with status_code in
        # the exception group (DELAY, HELD, EXCEPTION). The exact status
        # code set is customer-configurable.
        query = {"status_type_gid__like": "%EXCEPTION%"}
        raw = await self._find("SHIPMENT_STATUS", query=query)
        records = [self._map_shipment_status(r) for r in raw]
        return ExtractionResult(
            entity_type="exceptions",
            records_extracted=len(records),
            records_mapped=len(records),
            records_skipped=0,
            errors=[],
        )

    # ── Injection ──────────────────────────────────────────────────

    async def inject_carrier_assignment(
        self,
        shipment_external_id: str,
        carrier_id: str,
        rate: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InjectionResult:
        # TODO: POST to glog.webserver.shipment.ShipmentUpdateServlet with
        # SERVPROV_GID assignment. Customer-specific workflow (BUY_SHIPMENT
        # vs SELL_SHIPMENT vs direct tender) determines the exact payload.
        return InjectionResult(
            decision_id=(metadata or {}).get("id", 0),
            decision_type="carrier_assignment",
            success=False,
            error="Oracle OTM inject_carrier_assignment not yet implemented",
        )

    async def inject_appointment_change(
        self,
        appointment_external_id: str,
        new_start: datetime,
        new_end: datetime,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InjectionResult:
        return InjectionResult(
            decision_id=(metadata or {}).get("id", 0),
            decision_type="appointment_change",
            success=False,
            error="Oracle OTM inject_appointment_change not yet implemented",
        )

    async def inject_load_plan(
        self,
        load_external_id: str,
        shipment_ids: List[str],
        equipment_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InjectionResult:
        return InjectionResult(
            decision_id=(metadata or {}).get("id", 0),
            decision_type="load_plan",
            success=False,
            error="Oracle OTM inject_load_plan not yet implemented",
        )

    # ── Mapping (minimal — expand per engagement) ──────────────────

    @staticmethod
    def _map_shipment(raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "shipment_number": raw.get("SHIPMENT_GID", ""),
            "external_id": raw.get("SHIPMENT_GID", ""),
            "source": "ORACLE_OTM",
            "status": raw.get("SHIPMENT_STATUS_GID", ""),
            "transport_mode": raw.get("TRANSPORT_MODE_GID", ""),
            "carrier_vendor_number": raw.get("SERVPROV_GID", ""),
            "origin_facility": raw.get("SOURCE_LOCATION_GID", ""),
            "destination_facility": raw.get("DEST_LOCATION_GID", ""),
            "planned_pickup_date": raw.get("START_TIME"),
            "planned_delivery_date": raw.get("END_TIME"),
            "total_weight": raw.get("TOTAL_WEIGHT"),
            "weight_uom": raw.get("WEIGHT_UOM_CODE"),
        }

    @staticmethod
    def _map_order_movement(raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "shipment_number": raw.get("ORDER_MOVEMENT_GID", ""),
            "leg_sequence": raw.get("ORDER_MOVEMENT_SEQ_NUM", 0),
            "transport_mode": raw.get("TRANSPORT_MODE_GID", ""),
            "source": "ORACLE_OTM",
        }

    @staticmethod
    def _map_servprov(raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "vendor_number": raw.get("SERVPROV_GID", ""),
            "name": raw.get("NAME", ""),
            "scac": raw.get("SCAC", "") or None,
            "source": "ORACLE_OTM",
        }

    @staticmethod
    def _map_rate_offering(raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "rate_id": raw.get("RATE_OFFERING_GID", ""),
            "carrier_vendor_number": raw.get("SERVPROV_GID", ""),
            "source_region": raw.get("SOURCE_REGION_GID", ""),
            "dest_region": raw.get("DEST_REGION_GID", ""),
            "effective_date": raw.get("EFFECTIVE_DATE"),
            "expiration_date": raw.get("EXPIRATION_DATE"),
            "source": "ORACLE_OTM",
        }

    @staticmethod
    def _map_shipment_stop(raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "shipment_number": raw.get("SHIPMENT_GID", ""),
            "external_id": f"{raw.get('SHIPMENT_GID', '')}-{raw.get('STOP_NUM', '')}",
            "appointment_type": raw.get("STOP_TYPE_GID", ""),
            "facility": raw.get("LOCATION_GID", ""),
            "planned_start": raw.get("PLANNED_ARRIVAL"),
            "planned_end": raw.get("PLANNED_DEPARTURE"),
            "actual_start": raw.get("ACTUAL_ARRIVAL"),
            "source": "ORACLE_OTM",
        }

    @staticmethod
    def _map_shipment_status(raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "shipment_number": raw.get("SHIPMENT_GID", ""),
            "exception_type": raw.get("STATUS_TYPE_GID", "EXCEPTION"),
            "severity": "HIGH",
            "detected_at": raw.get("STATUS_DATE"),
            "source": "ORACLE_OTM",
        }
