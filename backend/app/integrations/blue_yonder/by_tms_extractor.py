"""
Blue Yonder TMS (formerly JDA TMS) Extraction Adapter — SKELETON.

Blue Yonder's TMS is REST-native with OAuth2 client-credentials auth
(Luminate platform). This adapter is the thinnest of the three vendor
skeletons because BY's APIs are JSON-native and well-documented.

Endpoints (Luminate TMS v2):
    POST /auth/oauth2/token                        (OAuth2 token)
    GET  /api/tms/v2/orders                        (shipments / loads)
    GET  /api/tms/v2/carriers                      (carrier master)
    GET  /api/tms/v2/rates                         (rate agreements)
    GET  /api/tms/v2/appointments                  (dock appointments)
    GET  /api/tms/v2/exceptions                    (shipment exceptions)
    PATCH /api/tms/v2/orders/{id}/carrier          (carrier assignment)
    PATCH /api/tms/v2/appointments/{id}            (appointment change)
    POST /api/tms/v2/orders/{id}/consolidate       (load plan)

See docs/TMS_ERP_INTEGRATION.md § "Blue Yonder TMS-specific data mapping".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
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
class BlueYonderTMSConnectionConfig(ConnectionConfig):
    base_url: Optional[str] = None          # e.g. https://luminate.blueyonder.com
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    tenant_code: Optional[str] = None       # BY tenant identifier
    verify_ssl: bool = True


class BlueYonderTMSAdapter(TMSExtractionAdapter):
    """Blue Yonder TMS extraction/injection adapter — skeleton.

    OAuth2 client-credentials flow with token caching. JSON over REST
    for all extraction and injection. Mapping bodies are minimal —
    expand per customer engagement.
    """

    def __init__(self, config: BlueYonderTMSConnectionConfig):
        super().__init__(config)
        self.config: BlueYonderTMSConnectionConfig = config
        self._client = None
        self._token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    # ── Connection / auth ───────────────────────────────────────────

    async def connect(self) -> bool:
        try:
            import httpx
            if not self.config.base_url:
                logger.error("Blue Yonder base_url not configured")
                return False
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                verify=self.config.verify_ssl,
                timeout=120.0,
            )
            ok = await self._refresh_token()
            self._connected = ok
            return ok
        except Exception as e:
            logger.error("Blue Yonder connect failed: %s", e)
            self._connected = False
            return False

    async def _refresh_token(self) -> bool:
        if not self._client:
            return False
        try:
            resp = await self._client.post(
                "/auth/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.config.client_id or "",
                    "client_secret": self.config.client_secret or "",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code != 200:
                logger.error(
                    "BY token refresh HTTP %s: %s",
                    resp.status_code, resp.text[:200],
                )
                return False
            data = resp.json()
            self._token = data["access_token"]
            # Subtract 60s as safety buffer
            from datetime import timedelta
            self._token_expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=max(60, int(data.get("expires_in", 3600)) - 60),
            )
            return True
        except Exception as e:
            logger.error("BY token refresh failed: %s", e)
            return False

    def _auth_headers(self) -> Dict[str, str]:
        h = {"Accept": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        if self.config.tenant_code:
            h["X-BY-Tenant"] = self.config.tenant_code
        return h

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None
        self._token = None
        self._connected = False

    async def test_connection(self) -> Dict[str, Any]:
        if not self._connected:
            ok = await self.connect()
            if not ok:
                return {"connected": False, "message": "BY connect failed"}
        return {"connected": True, "base_url": self.config.base_url}

    # ── REST helper ─────────────────────────────────────────────────

    async def _get(
        self, path: str, params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if not self._client:
            return []
        # Refresh token if expired
        if self._token_expires_at and datetime.now(timezone.utc) >= self._token_expires_at:
            await self._refresh_token()
        try:
            resp = await self._client.get(
                path, params=params, headers=self._auth_headers(),
            )
            if resp.status_code == 401:
                await self._refresh_token()
                resp = await self._client.get(
                    path, params=params, headers=self._auth_headers(),
                )
            if resp.status_code != 200:
                logger.warning("BY GET %s HTTP %s", path, resp.status_code)
                return []
            body = resp.json()
            # BY paginated responses come as {data: [...], meta: {...}}
            return body.get("data", body) if isinstance(body, dict) else body
        except Exception as e:
            logger.error("BY GET %s failed: %s", path, e)
            return []

    # ── Extraction ──────────────────────────────────────────────────

    async def extract_shipments(
        self,
        since: Optional[datetime] = None,
        mode: ExtractionMode = ExtractionMode.INCREMENTAL,
        batch_size: int = 500,
    ) -> ExtractionResult:
        params: Dict[str, Any] = {"limit": batch_size}
        if since and mode == ExtractionMode.INCREMENTAL:
            params["modifiedSince"] = since.isoformat()
        raw = await self._get("/api/tms/v2/orders", params=params)
        records = [self._map_order(r) for r in raw]
        return ExtractionResult(
            entity_type="shipments",
            records_extracted=len(records),
            records_mapped=len(records),
            records_skipped=0,
            errors=[],
        )

    async def extract_loads(
        self,
        since: Optional[datetime] = None,
        mode: ExtractionMode = ExtractionMode.INCREMENTAL,
        batch_size: int = 500,
    ) -> ExtractionResult:
        # BY uses the same /orders endpoint with a `?type=load` filter
        params: Dict[str, Any] = {"limit": batch_size, "type": "load"}
        raw = await self._get("/api/tms/v2/orders", params=params)
        return ExtractionResult(
            entity_type="loads",
            records_extracted=len(raw),
            records_mapped=len(raw),
            records_skipped=0,
            errors=[],
        )

    async def extract_carriers(
        self, mode: ExtractionMode = ExtractionMode.FULL,
    ) -> ExtractionResult:
        raw = await self._get("/api/tms/v2/carriers")
        records = [self._map_carrier(r) for r in raw]
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
        raw = await self._get("/api/tms/v2/rates")
        records = [self._map_rate(r) for r in raw]
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
        params: Dict[str, Any] = {}
        if since and mode == ExtractionMode.INCREMENTAL:
            params["modifiedSince"] = since.isoformat()
        raw = await self._get("/api/tms/v2/appointments", params=params)
        records = [self._map_appointment(r) for r in raw]
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
        params: Dict[str, Any] = {}
        if since and mode == ExtractionMode.INCREMENTAL:
            params["since"] = since.isoformat()
        raw = await self._get("/api/tms/v2/exceptions", params=params)
        records = [self._map_exception(r) for r in raw]
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
        if not self._client:
            return InjectionResult(
                decision_id=(metadata or {}).get("id", 0),
                decision_type="carrier_assignment",
                success=False,
                error="BY HTTP client not connected",
            )
        try:
            payload = {"carrierId": carrier_id}
            if rate is not None:
                payload["rate"] = rate
            resp = await self._client.patch(
                f"/api/tms/v2/orders/{shipment_external_id}/carrier",
                json=payload,
                headers=self._auth_headers(),
            )
            return InjectionResult(
                decision_id=(metadata or {}).get("id", 0),
                decision_type="carrier_assignment",
                success=resp.status_code < 300,
                external_id=shipment_external_id,
                response=resp.json() if resp.status_code < 300 else None,
                error=None if resp.status_code < 300 else resp.text[:300],
            )
        except Exception as e:
            return InjectionResult(
                decision_id=(metadata or {}).get("id", 0),
                decision_type="carrier_assignment",
                success=False,
                error=str(e),
            )

    async def inject_appointment_change(
        self,
        appointment_external_id: str,
        new_start: datetime,
        new_end: datetime,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InjectionResult:
        if not self._client:
            return InjectionResult(
                decision_id=(metadata or {}).get("id", 0),
                decision_type="appointment_change",
                success=False,
                error="BY HTTP client not connected",
            )
        try:
            payload = {
                "scheduledStart": new_start.isoformat(),
                "scheduledEnd": new_end.isoformat(),
            }
            resp = await self._client.patch(
                f"/api/tms/v2/appointments/{appointment_external_id}",
                json=payload,
                headers=self._auth_headers(),
            )
            return InjectionResult(
                decision_id=(metadata or {}).get("id", 0),
                decision_type="appointment_change",
                success=resp.status_code < 300,
                external_id=appointment_external_id,
                response=resp.json() if resp.status_code < 300 else None,
                error=None if resp.status_code < 300 else resp.text[:300],
            )
        except Exception as e:
            return InjectionResult(
                decision_id=(metadata or {}).get("id", 0),
                decision_type="appointment_change",
                success=False,
                error=str(e),
            )

    async def inject_load_plan(
        self,
        load_external_id: str,
        shipment_ids: List[str],
        equipment_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InjectionResult:
        if not self._client:
            return InjectionResult(
                decision_id=(metadata or {}).get("id", 0),
                decision_type="load_plan",
                success=False,
                error="BY HTTP client not connected",
            )
        try:
            payload: Dict[str, Any] = {"orderIds": shipment_ids}
            if equipment_type:
                payload["equipmentType"] = equipment_type
            resp = await self._client.post(
                f"/api/tms/v2/orders/{load_external_id}/consolidate",
                json=payload,
                headers=self._auth_headers(),
            )
            return InjectionResult(
                decision_id=(metadata or {}).get("id", 0),
                decision_type="load_plan",
                success=resp.status_code < 300,
                external_id=load_external_id,
                response=resp.json() if resp.status_code < 300 else None,
                error=None if resp.status_code < 300 else resp.text[:300],
            )
        except Exception as e:
            return InjectionResult(
                decision_id=(metadata or {}).get("id", 0),
                decision_type="load_plan",
                success=False,
                error=str(e),
            )

    # ── Mapping (minimal — expand per engagement) ──────────────────

    @staticmethod
    def _map_order(raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "shipment_number": raw.get("orderId", ""),
            "external_id": raw.get("orderId", ""),
            "source": "BLUE_YONDER",
            "status": raw.get("status", ""),
            "transport_mode": raw.get("mode", ""),
            "carrier_vendor_number": raw.get("carrierId", ""),
            "origin_facility": raw.get("originId", ""),
            "destination_facility": raw.get("destinationId", ""),
            "planned_pickup_date": raw.get("pickupDate"),
            "planned_delivery_date": raw.get("deliveryDate"),
            "total_weight": raw.get("weight"),
            "weight_uom": raw.get("weightUom"),
        }

    @staticmethod
    def _map_carrier(raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "vendor_number": raw.get("carrierId", ""),
            "name": raw.get("name", ""),
            "scac": raw.get("scac") or None,
            "is_blocked": bool(raw.get("inactive", False)),
            "source": "BLUE_YONDER",
        }

    @staticmethod
    def _map_rate(raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "rate_id": raw.get("rateId", ""),
            "carrier_vendor_number": raw.get("carrierId", ""),
            "origin_region": raw.get("origin", ""),
            "dest_region": raw.get("destination", ""),
            "amount": raw.get("amount"),
            "currency": raw.get("currency"),
            "effective_date": raw.get("effectiveFrom"),
            "expiration_date": raw.get("effectiveTo"),
            "source": "BLUE_YONDER",
        }

    @staticmethod
    def _map_appointment(raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "shipment_number": raw.get("orderId", ""),
            "external_id": raw.get("appointmentId", ""),
            "appointment_type": raw.get("type", ""),
            "facility": raw.get("locationId", ""),
            "planned_start": raw.get("scheduledStart"),
            "planned_end": raw.get("scheduledEnd"),
            "actual_start": raw.get("actualStart"),
            "source": "BLUE_YONDER",
        }

    @staticmethod
    def _map_exception(raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "shipment_number": raw.get("orderId", ""),
            "exception_type": raw.get("type", "EXCEPTION"),
            "severity": raw.get("severity", "HIGH"),
            "detected_at": raw.get("detectedAt"),
            "source": "BLUE_YONDER",
        }
