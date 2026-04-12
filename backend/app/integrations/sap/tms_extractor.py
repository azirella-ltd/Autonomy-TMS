"""
SAP TM Extraction Adapter

Extracts transportation management data from SAP S/4HANA TM module
into Autonomy TMS canonical entities. Uses the existing S4HANAConnector
for RFC-based access and ODataExtractor for API-based access.

SAP TM Tables:
- VTTK: Shipment Header (Freight Order)
- VTTS: Shipment Stage (Freight Unit / Leg)
- VTSP: Shipment Item (Freight Unit Item)
- VTTP: Shipment Item (Package Item)
- VFKK: Freight Cost Document Header
- VFKP: Freight Cost Document Item
- LIKP: Delivery Header (outbound delivery → BOL)
- LIPS: Delivery Item
- LFA1: Vendor Master (carriers)
- ADRC: Address Master
- EKKO: Purchasing Doc Header (scheduling agreements = carrier contracts)
- EKPO: Purchasing Doc Item

OData Services (S/4HANA Cloud):
- API_FREIGHT_ORDER: Freight Order CRUD
- API_BUSINESS_PARTNER: Business Partner (carrier) read
- API_PRODUCT: Product/Material master

See docs/TMS_ERP_INTEGRATION.md for the full entity mapping.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.tms_adapter import (
    TMSExtractionAdapter,
    ConnectionConfig,
    ExtractionMode,
    ExtractionResult,
    InjectionResult,
)

logger = logging.getLogger(__name__)


# ── SAP TM Table Definitions ────────────────────────────────────────────────

# Freight Order header (VTTK or API_FREIGHT_ORDER)
FREIGHT_ORDER_FIELDS = [
    "TKNUM",    # Shipment Number
    "SHTYP",    # Shipment Type
    "STTRG",    # Status (Overall Transportation Status)
    "ERDAT",    # Created Date
    "ERZET",    # Created Time
    "AEDAT",    # Changed Date
    "VSART",    # Shipping Type (mode)
    "TDLNR",    # Forwarding Agent (carrier vendor number)
    "SIGNI",    # External ID / Reference
    "DTABF",    # Planned Departure Date
    "UZABF",    # Planned Departure Time
    "DTANK",    # Planned Arrival Date
    "UZANK",    # Planned Arrival Time
    "DTEFB",    # Actual Departure Date
    "DTEFA",    # Actual Arrival Date
    "ABFER",    # Departure Facility (plant/loading point)
    "EZESSION", # Destination Facility
    "VSBED",    # Shipping Conditions
    "ROUTE",    # Route
    "TNDR_TRKID", # Tender Tracking ID
    "TNDR_STS", # Tender Status
    "BTGEW",    # Total Weight
    "GEWEI",    # Weight Unit
    "VOLUM",    # Total Volume
    "VOLEH",    # Volume Unit
    "ANZFH",    # Number of Handling Units
    "EXTI1",    # External ID 1 (PRO number, BOL)
    "EXTI2",    # External ID 2
]

# Freight Unit / Shipment Stage (VTTS)
FREIGHT_STAGE_FIELDS = [
    "TKNUM",    # Shipment Number (FK to VTTK)
    "TSNUM",    # Stage Number
    "TSTYP",    # Stage Type
    "VSART",    # Shipping Type (mode for this leg)
    "TDLNR",    # Carrier for this leg
    "WERKA",    # Origin Plant
    "WERKB",    # Destination Plant
    "DTEFB",    # Actual Departure Date
    "DTEFA",    # Actual Arrival Date
    "BTGEW",    # Weight
    "VOLUM",    # Volume
]

# Freight Cost Document (VFKP)
FREIGHT_COST_FIELDS = [
    "VFKNUM",   # Freight Cost Doc Number
    "VFKPOS",   # Item Number
    "TKNUM",    # Shipment Number (FK to VTTK)
    "LIFNR",    # Vendor (carrier)
    "KSCHL",    # Condition Type (rate type)
    "KWERT",    # Amount
    "WAERK",    # Currency
    "MENGE",    # Quantity
    "MEINS",    # Unit of Measure
]

# Carrier Master (subset of LFA1 with transport-specific fields)
CARRIER_FIELDS = [
    "LIFNR",    # Vendor Number
    "NAME1",    # Name 1
    "NAME2",    # Name 2
    "LAND1",    # Country
    "ADRNR",    # Address Number (FK to ADRC)
    "STCD1",    # Tax Number 1 (can be MC#)
    "STCD2",    # Tax Number 2 (can be DOT#)
    "SCAC",     # Standard Carrier Alpha Code (Z-field on many SAP systems)
    "TELF1",    # Phone
    "TELFX",    # Fax
    "KTOKK",    # Account Group
    "LOEVM",    # Deletion Flag
    "SPERR",    # Posting Block
]


@dataclass
class SAPTMConnectionConfig(ConnectionConfig):
    """SAP TM-specific connection configuration."""
    # RFC connection (for on-premise S/4HANA)
    ashost: Optional[str] = None
    sysnr: str = "00"
    client: str = "100"
    sap_user: Optional[str] = None
    sap_password: Optional[str] = None
    # OData connection (for S/4HANA Cloud)
    odata_base_url: Optional[str] = None
    odata_client_id: Optional[str] = None
    odata_client_secret: Optional[str] = None
    # Which extraction method to prefer
    preferred_method: str = "odata"  # "odata", "rfc", "csv"
    # SAP system filters
    company_code: Optional[str] = None
    plant_filter: Optional[List[str]] = None
    shipping_type_filter: Optional[List[str]] = None  # e.g., ["01", "02"] for truck, rail


class SAPTMAdapter(TMSExtractionAdapter):
    """
    SAP TM extraction adapter.

    Extracts freight orders, carriers, rates, and appointments from
    SAP S/4HANA TM module. Reuses the existing S4HANAConnector for
    RFC-based access.

    Supports:
    - Freight Orders (VTTK) → TMS Shipment + Load
    - Freight Stages (VTTS) → TMS ShipmentLeg
    - Freight Costs (VFKP) → TMS FreightRate
    - Carrier Master (LFA1) → TMS Carrier (extends TradingPartner)
    - Scheduling Agreements (EKKO/EKPO SA type) → TMS CarrierContract
    - Deliveries (LIKP/LIPS) → TMS BillOfLading
    - Shipment Status (VTTK-STTRG) → TMS TrackingEvent
    """

    def __init__(self, config: SAPTMConnectionConfig):
        super().__init__(config)
        self.config: SAPTMConnectionConfig = config
        self._connector = None
        self._odata_extractor = None

    # ── Connection Management ────────────────────────────────────────────

    async def connect(self) -> bool:
        """Establish connection to SAP S/4HANA."""
        try:
            if self.config.preferred_method == "rfc" and self.config.ashost:
                from .s4hana_connector import S4HANAConnector, S4HANAConnectionConfig
                rfc_config = S4HANAConnectionConfig(
                    ashost=self.config.ashost,
                    sysnr=self.config.sysnr,
                    client=self.config.client,
                    user=self.config.sap_user or "",
                    passwd=self.config.sap_password or "",
                )
                self._connector = S4HANAConnector(rfc_config)
                self._connected = self._connector.connect()
            elif self.config.preferred_method == "odata" and self.config.odata_base_url:
                from .extractors import ODataExtractor
                self._odata_extractor = ODataExtractor(
                    base_url=self.config.odata_base_url,
                    client_id=self.config.odata_client_id or "",
                    client_secret=self.config.odata_client_secret or "",
                )
                connected, msg = await self._odata_extractor.test_connection()
                self._connected = connected
                if not connected:
                    logger.error(f"SAP TM OData connection failed: {msg}")
            else:
                logger.error(f"No valid SAP connection config for method {self.config.preferred_method}")
                self._connected = False

            return self._connected
        except Exception as e:
            logger.error(f"SAP TM connection failed: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Close the SAP connection."""
        if self._connector:
            self._connector.disconnect()
        self._connector = None
        self._odata_extractor = None
        self._connected = False

    async def test_connection(self) -> Dict[str, Any]:
        """Test SAP TM connectivity."""
        if not self._connected:
            try:
                connected = await self.connect()
                if not connected:
                    return {"connected": False, "message": "Connection failed"}
            except Exception as e:
                return {"connected": False, "message": str(e)}
        return {
            "connected": True,
            "method": self.config.preferred_method,
            "message": "SAP TM connection active",
        }

    # ── Extraction Methods ───────────────────────────────────────────────

    async def extract_shipments(
        self,
        since: Optional[datetime] = None,
        mode: ExtractionMode = ExtractionMode.INCREMENTAL,
        batch_size: int = 500,
    ) -> ExtractionResult:
        """
        Extract Freight Orders from SAP TM (VTTK) → TMS Shipment + Load.

        Maps:
        - TKNUM → shipment_number
        - STTRG → status (via SAP status mapping)
        - VSART → transport_mode (via mode mapping)
        - TDLNR → carrier_id (vendor number lookup)
        - DTABF/UZABF → planned_pickup_date
        - DTANK/UZANK → planned_delivery_date
        - DTEFB → actual_pickup_date
        - DTEFA → actual_delivery_date
        - ABFER → origin_site_id
        - EZESSION → destination_site_id
        - BTGEW/GEWEI → total_weight / weight_uom
        - EXTI1 → reference_numbers.pro / reference_numbers.bol
        """
        start = datetime.utcnow()
        records = []
        errors = []

        try:
            if self._connector:
                # RFC extraction
                where_clause = ""
                if since and mode == ExtractionMode.INCREMENTAL:
                    since_str = since.strftime("%Y%m%d")
                    where_clause = f"AEDAT >= '{since_str}'"

                df = self._connector._execute_query(
                    "VTTK",
                    FREIGHT_ORDER_FIELDS,
                    where_clause=where_clause,
                    max_rows=batch_size if mode != ExtractionMode.HISTORICAL else 0,
                )
                records = self._map_freight_orders(df)

            elif self._odata_extractor:
                # OData extraction
                filters = []
                if since and mode == ExtractionMode.INCREMENTAL:
                    filters.append(f"LastChangeDateTime ge datetime'{since.isoformat()}'")

                raw = await self._odata_extractor._fetch_entity_set(
                    "API_FREIGHT_ORDER",
                    "A_FreightOrder",
                    filters=filters,
                    top=batch_size if mode != ExtractionMode.HISTORICAL else None,
                )
                records = self._map_freight_orders_odata(raw)

        except Exception as e:
            logger.error(f"SAP TM shipment extraction failed: {e}")
            errors.append({"error": str(e), "phase": "extraction"})

        duration = (datetime.utcnow() - start).total_seconds()
        return ExtractionResult(
            entity_type="shipments",
            records_extracted=len(records),
            records_mapped=len(records),
            records_skipped=0,
            errors=errors,
            duration_seconds=duration,
            watermark=datetime.utcnow().isoformat() if records else None,
        )

    async def extract_loads(
        self,
        since: Optional[datetime] = None,
        mode: ExtractionMode = ExtractionMode.INCREMENTAL,
        batch_size: int = 500,
    ) -> ExtractionResult:
        """
        Extract Freight Units/Stages from SAP TM (VTTS) → TMS Load.

        In SAP TM, a Freight Order (VTTK) can have multiple stages (VTTS),
        each representing a leg. The Freight Order itself maps to TMS Load;
        stages map to ShipmentLeg.
        """
        start = datetime.utcnow()
        records = []
        errors = []

        try:
            if self._connector:
                where_clause = ""
                if since and mode == ExtractionMode.INCREMENTAL:
                    since_str = since.strftime("%Y%m%d")
                    where_clause = f"ERDAT >= '{since_str}'"

                df = self._connector._execute_query(
                    "VTTS",
                    FREIGHT_STAGE_FIELDS,
                    where_clause=where_clause,
                    max_rows=batch_size if mode != ExtractionMode.HISTORICAL else 0,
                )
                records = [self._map_freight_stage(row) for _, row in df.iterrows()]

        except Exception as e:
            logger.error(f"SAP TM load extraction failed: {e}")
            errors.append({"error": str(e), "phase": "extraction"})

        duration = (datetime.utcnow() - start).total_seconds()
        return ExtractionResult(
            entity_type="loads",
            records_extracted=len(records),
            records_mapped=len(records),
            records_skipped=0,
            errors=errors,
            duration_seconds=duration,
        )

    async def extract_carriers(
        self,
        mode: ExtractionMode = ExtractionMode.FULL,
    ) -> ExtractionResult:
        """
        Extract Carrier Master from SAP (LFA1 filtered by transport flag) → TMS Carrier.

        Enriches the canonical TradingPartner with carrier-specific fields:
        SCAC, MC#, DOT#, account group, equipment capabilities.
        """
        start = datetime.utcnow()
        records = []
        errors = []

        try:
            if self._connector:
                # LFA1 vendors with transport-relevant account groups
                # Account groups '0001' (vendor) filtered by transport usage
                df = self._connector._execute_query(
                    "LFA1",
                    CARRIER_FIELDS,
                    where_clause="KTOKK IN ('0001', 'TRAN', 'CARR')",
                    max_rows=0,  # All carriers
                )
                records = [self._map_carrier(row) for _, row in df.iterrows()]

        except Exception as e:
            logger.error(f"SAP TM carrier extraction failed: {e}")
            errors.append({"error": str(e), "phase": "extraction"})

        duration = (datetime.utcnow() - start).total_seconds()
        return ExtractionResult(
            entity_type="carriers",
            records_extracted=len(records),
            records_mapped=len(records),
            records_skipped=0,
            errors=errors,
            duration_seconds=duration,
        )

    async def extract_rates(
        self,
        mode: ExtractionMode = ExtractionMode.FULL,
    ) -> ExtractionResult:
        """
        Extract Freight Costs from SAP TM (VFKP) → TMS FreightRate.
        """
        start = datetime.utcnow()
        records = []
        errors = []

        try:
            if self._connector:
                df = self._connector._execute_query(
                    "VFKP",
                    FREIGHT_COST_FIELDS,
                    max_rows=0,
                )
                records = [self._map_freight_cost(row) for _, row in df.iterrows()]

        except Exception as e:
            logger.error(f"SAP TM rate extraction failed: {e}")
            errors.append({"error": str(e), "phase": "extraction"})

        duration = (datetime.utcnow() - start).total_seconds()
        return ExtractionResult(
            entity_type="rates",
            records_extracted=len(records),
            records_mapped=len(records),
            records_skipped=0,
            errors=errors,
            duration_seconds=duration,
        )

    async def extract_appointments(
        self,
        since: Optional[datetime] = None,
        mode: ExtractionMode = ExtractionMode.INCREMENTAL,
    ) -> ExtractionResult:
        """
        Extract appointment data from SAP TM.

        SAP TM doesn't have a dedicated appointment table — appointments
        are derived from Freight Order planned dates + Delivery scheduling.
        This method extracts the planned pickup/delivery windows from VTTK.
        """
        # Appointments in SAP TM are part of the Freight Order — reuse
        # the shipment extraction with appointment-focused mapping
        return ExtractionResult(
            entity_type="appointments",
            records_extracted=0,
            records_mapped=0,
            records_skipped=0,
            errors=[{"info": "SAP TM appointments derived from Freight Order dates during shipment extraction"}],
        )

    async def extract_exceptions(
        self,
        since: Optional[datetime] = None,
        mode: ExtractionMode = ExtractionMode.INCREMENTAL,
    ) -> ExtractionResult:
        """
        Extract shipment exceptions from SAP TM.

        SAP TM exceptions surface through event management (EM) or as
        status changes on freight orders. This method checks for orders
        with exception-indicating statuses.
        """
        start = datetime.utcnow()
        records = []
        errors = []

        try:
            if self._connector:
                # STTRG values that indicate exceptions
                exception_statuses = "'0004', '0005', '0006'"  # Delayed, Issue, Failed
                where_clause = f"STTRG IN ({exception_statuses})"
                if since:
                    since_str = since.strftime("%Y%m%d")
                    where_clause += f" AND AEDAT >= '{since_str}'"

                df = self._connector._execute_query(
                    "VTTK",
                    ["TKNUM", "STTRG", "AEDAT", "ERZET", "SIGNI", "TDLNR"],
                    where_clause=where_clause,
                    max_rows=500,
                )
                records = [self._map_exception(row) for _, row in df.iterrows()]

        except Exception as e:
            logger.error(f"SAP TM exception extraction failed: {e}")
            errors.append({"error": str(e), "phase": "extraction"})

        duration = (datetime.utcnow() - start).total_seconds()
        return ExtractionResult(
            entity_type="exceptions",
            records_extracted=len(records),
            records_mapped=len(records),
            records_skipped=0,
            errors=errors,
            duration_seconds=duration,
        )

    # ── Injection Methods ────────────────────────────────────────────────

    async def inject_carrier_assignment(
        self,
        shipment_external_id: str,
        carrier_id: str,
        rate: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InjectionResult:
        """
        Assign a carrier to a Freight Order in SAP TM.

        Uses BAPI_SHIPMENT_CHANGE to update TDLNR (forwarding agent)
        on the Freight Order identified by TKNUM.
        """
        try:
            if self._connector:
                result = self._connector.execute_bapi(
                    "BAPI_SHIPMENT_CHANGE",
                    HEADERDATA={"SHIPMENT_NUM": shipment_external_id},
                    HEADERDATAX={"SHIPMENT_NUM": "X"},
                    DEADLINES=[],
                    PARTNERADDRESSES=[{
                        "FORWAGENT": carrier_id,
                    }],
                )
                return InjectionResult(
                    decision_id=metadata.get("id", 0) if metadata else 0,
                    decision_type="carrier_assignment",
                    success=not result.get("RETURN", [{}])[0].get("TYPE") == "E",
                    external_id=shipment_external_id,
                    response=result,
                )
            else:
                return InjectionResult(
                    decision_id=metadata.get("id", 0) if metadata else 0,
                    decision_type="carrier_assignment",
                    success=False,
                    error="No RFC connection available for BAPI call",
                )
        except Exception as e:
            return InjectionResult(
                decision_id=metadata.get("id", 0) if metadata else 0,
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
        """Update planned dates on a Freight Order."""
        try:
            if self._connector:
                result = self._connector.execute_bapi(
                    "BAPI_SHIPMENT_CHANGE",
                    HEADERDATA={"SHIPMENT_NUM": appointment_external_id},
                    DEADLINES=[{
                        "DATTYP": "PLND",  # Planned departure
                        "DATE": new_start.strftime("%Y%m%d"),
                        "TIME": new_start.strftime("%H%M%S"),
                    }, {
                        "DATTYP": "PLNA",  # Planned arrival
                        "DATE": new_end.strftime("%Y%m%d"),
                        "TIME": new_end.strftime("%H%M%S"),
                    }],
                )
                return InjectionResult(
                    decision_id=metadata.get("id", 0) if metadata else 0,
                    decision_type="appointment_change",
                    success=not result.get("RETURN", [{}])[0].get("TYPE") == "E",
                    external_id=appointment_external_id,
                    response=result,
                )
            return InjectionResult(
                decision_id=0, decision_type="appointment_change",
                success=False, error="No RFC connection",
            )
        except Exception as e:
            return InjectionResult(
                decision_id=0, decision_type="appointment_change",
                success=False, error=str(e),
            )

    async def inject_load_plan(
        self,
        load_external_id: str,
        shipment_ids: List[str],
        equipment_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InjectionResult:
        """
        Update load composition on a Freight Order in SAP TM.

        This is a complex operation in SAP — typically involves
        BAPI_SHIPMENT_CHANGE to reassign delivery documents to a
        different shipment number.
        """
        # Load plan injection is SAP TM's most complex operation —
        # requires orchestrating multiple BAPIs. Placeholder for now.
        logger.warning(
            f"SAP TM load plan injection not yet implemented. "
            f"Load {load_external_id}, shipments {shipment_ids}"
        )
        return InjectionResult(
            decision_id=metadata.get("id", 0) if metadata else 0,
            decision_type="load_plan",
            success=False,
            error="Load plan injection not yet implemented for SAP TM",
        )

    # ── Private Mapping Methods ──────────────────────────────────────────

    def _map_freight_orders(self, df) -> List[Dict[str, Any]]:
        """Map SAP VTTK DataFrame to TMS Shipment dicts."""
        records = []
        for _, row in df.iterrows():
            records.append({
                "shipment_number": str(row.get("TKNUM", "")).strip(),
                "external_id": str(row.get("TKNUM", "")).strip(),
                "source": "SAP_TM",
                "status": self._map_sap_status(row.get("STTRG", "")),
                "transport_mode": self._map_sap_mode(row.get("VSART", "")),
                "carrier_vendor_number": str(row.get("TDLNR", "")).strip(),
                "planned_pickup_date": self._parse_sap_datetime(
                    row.get("DTABF"), row.get("UZABF")
                ),
                "planned_delivery_date": self._parse_sap_datetime(
                    row.get("DTANK"), row.get("UZANK")
                ),
                "actual_pickup_date": self._parse_sap_date(row.get("DTEFB")),
                "actual_delivery_date": self._parse_sap_date(row.get("DTEFA")),
                "origin_facility": str(row.get("ABFER", "")).strip(),
                "destination_facility": str(row.get("EZESSION", "")).strip(),
                "total_weight": row.get("BTGEW"),
                "weight_uom": str(row.get("GEWEI", "")).strip(),
                "total_volume": row.get("VOLUM"),
                "volume_uom": str(row.get("VOLEH", "")).strip(),
                "reference_numbers": {
                    "pro": str(row.get("EXTI1", "")).strip() or None,
                    "bol": str(row.get("EXTI2", "")).strip() or None,
                    "sap_shipment": str(row.get("TKNUM", "")).strip(),
                },
                "tender_status": str(row.get("TNDR_STS", "")).strip() or None,
                "tender_tracking_id": str(row.get("TNDR_TRKID", "")).strip() or None,
                "created_at": self._parse_sap_datetime(
                    row.get("ERDAT"), row.get("ERZET")
                ),
            })
        return records

    def _map_freight_orders_odata(self, raw: List[Dict]) -> List[Dict[str, Any]]:
        """Map SAP OData API_FREIGHT_ORDER response to TMS Shipment dicts."""
        records = []
        for item in raw:
            records.append({
                "shipment_number": item.get("FreightOrder", ""),
                "external_id": item.get("FreightOrder", ""),
                "source": "SAP_TM",
                "status": self._map_sap_status(item.get("TransportationStatus", "")),
                "transport_mode": self._map_sap_mode(item.get("TransportationMode", "")),
                "carrier_vendor_number": item.get("Carrier", ""),
                "planned_pickup_date": item.get("PlannedPickUpDateTime"),
                "planned_delivery_date": item.get("PlannedDeliveryDateTime"),
                "actual_pickup_date": item.get("ActualPickUpDateTime"),
                "actual_delivery_date": item.get("ActualDeliveryDateTime"),
                "total_weight": item.get("GrossWeight"),
                "weight_uom": item.get("GrossWeightUnit"),
                "reference_numbers": {
                    "sap_freight_order": item.get("FreightOrder"),
                },
                "created_at": item.get("CreationDateTime"),
            })
        return records

    def _map_freight_stage(self, row) -> Dict[str, Any]:
        """Map SAP VTTS row to TMS ShipmentLeg dict."""
        return {
            "shipment_number": str(row.get("TKNUM", "")).strip(),
            "leg_sequence": int(row.get("TSNUM", 0)),
            "leg_type": str(row.get("TSTYP", "")).strip(),
            "transport_mode": self._map_sap_mode(row.get("VSART", "")),
            "carrier_vendor_number": str(row.get("TDLNR", "")).strip(),
            "origin_plant": str(row.get("WERKA", "")).strip(),
            "destination_plant": str(row.get("WERKB", "")).strip(),
            "actual_departure": self._parse_sap_date(row.get("DTEFB")),
            "actual_arrival": self._parse_sap_date(row.get("DTEFA")),
            "weight": row.get("BTGEW"),
            "volume": row.get("VOLUM"),
            "source": "SAP_TM",
        }

    def _map_carrier(self, row) -> Dict[str, Any]:
        """Map SAP LFA1 row to TMS Carrier dict."""
        return {
            "vendor_number": str(row.get("LIFNR", "")).strip(),
            "name": str(row.get("NAME1", "")).strip(),
            "name2": str(row.get("NAME2", "")).strip(),
            "country": str(row.get("LAND1", "")).strip(),
            "scac": str(row.get("SCAC", "")).strip() or None,
            "mc_number": str(row.get("STCD1", "")).strip() or None,
            "dot_number": str(row.get("STCD2", "")).strip() or None,
            "phone": str(row.get("TELF1", "")).strip() or None,
            "account_group": str(row.get("KTOKK", "")).strip(),
            "is_blocked": bool(row.get("SPERR")),
            "is_deleted": bool(row.get("LOEVM")),
            "source": "SAP_TM",
        }

    def _map_freight_cost(self, row) -> Dict[str, Any]:
        """Map SAP VFKP row to TMS FreightRate dict."""
        return {
            "shipment_number": str(row.get("TKNUM", "")).strip(),
            "carrier_vendor_number": str(row.get("LIFNR", "")).strip(),
            "condition_type": str(row.get("KSCHL", "")).strip(),
            "amount": float(row.get("KWERT", 0)),
            "currency": str(row.get("WAERK", "")).strip(),
            "quantity": float(row.get("MENGE", 0)),
            "uom": str(row.get("MEINS", "")).strip(),
            "source": "SAP_TM",
        }

    def _map_exception(self, row) -> Dict[str, Any]:
        """Map SAP VTTK exception-status row to TMS ShipmentException dict."""
        status_map = {
            "0004": "DELAY",
            "0005": "DAMAGE",
            "0006": "EXCEPTION",
        }
        return {
            "shipment_number": str(row.get("TKNUM", "")).strip(),
            "exception_type": status_map.get(str(row.get("STTRG", "")), "EXCEPTION"),
            "severity": "HIGH",
            "carrier_vendor_number": str(row.get("TDLNR", "")).strip(),
            "detected_at": self._parse_sap_datetime(
                row.get("AEDAT"), row.get("ERZET")
            ),
            "source": "SAP_TM",
        }

    # ── SAP Value Mapping ────────────────────────────────────────────────

    @staticmethod
    def _map_sap_status(sap_status: str) -> str:
        """Map SAP TM overall transportation status (STTRG) to TMS status."""
        mapping = {
            "0001": "DRAFT",         # Not yet started
            "0002": "TENDERED",      # Planned
            "0003": "IN_TRANSIT",    # In execution
            "0004": "EXCEPTION",     # Delayed
            "0005": "EXCEPTION",     # Issue
            "0006": "EXCEPTION",     # Failed
            "0007": "DELIVERED",     # Completed
            "0008": "CLOSED",        # Settled
        }
        return mapping.get(str(sap_status).strip(), "DRAFT")

    @staticmethod
    def _map_sap_mode(sap_vsart: str) -> str:
        """Map SAP shipping type (VSART) to TMS transport mode."""
        mapping = {
            "01": "FTL",           # Truck
            "02": "RAIL_CARLOAD",  # Rail
            "03": "AIR_STD",       # Air
            "04": "FCL",           # Ocean
            "05": "INTERMODAL",    # Intermodal
            "06": "LTL",           # LTL
            "07": "PARCEL",        # Parcel/Express
            "08": "DRAYAGE",       # Drayage
            "09": "BULK_OCEAN",    # Bulk
        }
        return mapping.get(str(sap_vsart).strip(), "FTL")

    @staticmethod
    def _parse_sap_date(sap_date) -> Optional[datetime]:
        """Parse SAP date (YYYYMMDD or '00000000') to datetime."""
        if not sap_date or str(sap_date).strip() in ("", "00000000", "0"):
            return None
        try:
            return datetime.strptime(str(sap_date).strip()[:8], "%Y%m%d")
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_sap_datetime(sap_date, sap_time=None) -> Optional[datetime]:
        """Parse SAP date + time to datetime."""
        dt = SAPTMAdapter._parse_sap_date(sap_date)
        if dt and sap_time and str(sap_time).strip() not in ("", "000000", "0"):
            try:
                t = str(sap_time).strip()[:6]
                dt = dt.replace(
                    hour=int(t[:2]), minute=int(t[2:4]), second=int(t[4:6])
                )
            except (ValueError, IndexError):
                pass
        return dt
