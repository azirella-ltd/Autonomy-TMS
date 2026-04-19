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
from sqlalchemy import text
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
    preferred_method: str = "odata"  # "odata", "rfc", "csv", "db_canonical"
    # CSV directory (for csv method)
    csv_directory: Optional[str] = None
    # SAP system filters
    company_code: Optional[str] = None
    plant_filter: Optional[List[str]] = None
    shipping_type_filter: Optional[List[str]] = None  # e.g., ["01", "02"] for truck, rail
    # DB canonical connection (reads from a Postgres DB with AWS SC DM tables —
    # e.g., SCP staging DB, SAP HANA data lake, or any system exporting canonical
    # Shipment/Site/Product/TransportationLane tables)
    db_canonical_url: Optional[str] = None
    db_canonical_config_id: Optional[int] = None  # supply_chain_configs.id to scope extraction


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
        self._db_engine = None  # For db_canonical method

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
            elif self.config.preferred_method == "csv":
                from .csv_loader import CSVDataLoader
                self._csv_loader = CSVDataLoader(self.config.csv_directory or "")
                tables = self._csv_loader.list_available_tables()
                self._connected = len(tables) > 0
                logger.info(f"SAP CSV loader: {len(tables)} tables available")
            elif self.config.preferred_method == "db_canonical" and self.config.db_canonical_url:
                from sqlalchemy import create_engine
                self._db_engine = create_engine(
                    self.config.db_canonical_url,
                    pool_size=2, max_overflow=0,
                    connect_args={"options": "-c default_transaction_read_only=on"},
                )
                with self._db_engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                self._connected = True
                logger.info("SAP DB canonical connection established")
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

            elif hasattr(self, '_csv_loader') and self._csv_loader:
                # CSV extraction — base S/4HANA uses LIKP/LIPS (deliveries)
                # instead of VTTK (TM freight orders)
                records = self._extract_shipments_from_csv(since, mode)

            elif self._odata_extractor:
                # OData extraction
                filters = []
                if since and mode == ExtractionMode.INCREMENTAL:
                    filters.append(f"LastChangeDateTime ge datetime'{since.isoformat()}'")

                raw = await self._odata_extractor._fetch_entity_set(
                    "API_FREIGHT_ORDER",
                    "A_FreightOrder",
                    filters=filters,
                    max_records=batch_size if mode != ExtractionMode.HISTORICAL else 0,
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

            elif self._odata_extractor:
                filters = []
                if since and mode == ExtractionMode.INCREMENTAL:
                    filters.append(f"LastChangeDateTime ge datetime'{since.isoformat()}'")
                raw = await self._odata_extractor._fetch_entity_set(
                    "API_FREIGHT_UNIT",
                    "A_FreightUnit",
                    filters=filters,
                    max_records=batch_size if mode != ExtractionMode.HISTORICAL else 0,
                )
                records = self._map_freight_units_odata(raw)

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

            elif self._odata_extractor:
                # API_BUSINESS_PARTNER filtered by forwarding-agent role (FLFR01).
                # Customers can override the filter via shipping_type_filter if
                # they use a non-standard role code for carriers.
                filters = ["BusinessPartnerRole eq 'FLFR01'"]
                raw = await self._odata_extractor._fetch_entity_set(
                    "API_BUSINESS_PARTNER",
                    "A_BusinessPartner",
                    filters=filters,
                    max_records=0,
                )
                records = self._map_carriers_odata(raw)

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

            elif self._odata_extractor:
                # SAP doesn't publish a standard OData service for VFKP
                # freight cost items in S/4HANA Cloud. Rates usually come
                # through CDS views the customer exposes (YY1_FREIGHTCOST_CDS)
                # or a custom service. Skip cleanly with an errors entry so
                # the caller can log that OData rate sync isn't wired.
                errors.append({
                    "info": "OData freight-rate extraction requires a customer-specific "
                            "CDS view (e.g. YY1_FREIGHTCOST_CDS); RFC path is authoritative.",
                    "phase": "extraction",
                })

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
        # SAP TM models appointments as planned-date pairs on the Freight
        # Order (pickup: DTABF+UZABF at ABFER, delivery: DTANK+UZANK at
        # EZESSION). We extract the date fields and split into two
        # appointment records per shipment — one pickup, one delivery —
        # so DockSchedulingTRM has a uniform shape to consume.
        start = datetime.utcnow()
        records: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []

        appt_fields = [
            "TKNUM", "ABFER", "EZESSION", "TDLNR",
            "DTABF", "UZABF", "DTANK", "UZANK",
            "DTEFB", "DTEFA", "SIGNI",
        ]

        try:
            if self._connector:
                where_clause = ""
                if since and mode == ExtractionMode.INCREMENTAL:
                    where_clause = f"AEDAT >= '{since.strftime('%Y%m%d')}'"
                df = self._connector._execute_query(
                    "VTTK", appt_fields, where_clause=where_clause, max_rows=0,
                )
                for _, row in df.iterrows():
                    records.extend(self._derive_appointments(row))

            elif self._odata_extractor:
                filters = []
                if since and mode == ExtractionMode.INCREMENTAL:
                    filters.append(
                        f"LastChangeDateTime ge datetime'{since.isoformat()}'"
                    )
                raw = await self._odata_extractor._fetch_entity_set(
                    "API_FREIGHT_ORDER",
                    "A_FreightOrder",
                    filters=filters,
                    max_records=0,
                )
                for item in raw:
                    records.extend(self._derive_appointments_odata(item))

        except Exception as e:
            logger.error(f"SAP TM appointment extraction failed: {e}")
            errors.append({"error": str(e), "phase": "extraction"})

        duration = (datetime.utcnow() - start).total_seconds()
        return ExtractionResult(
            entity_type="appointments",
            records_extracted=len(records),
            records_mapped=len(records),
            records_skipped=0,
            errors=errors,
            duration_seconds=duration,
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

            elif self._odata_extractor:
                # Same API_FREIGHT_ORDER service, status-filtered. SAP uses
                # TransportationStatus code values "0004"-"0006" for the
                # delay/damage/failed triad (matches STTRG on RFC path).
                filters = ["TransportationStatus ge '0004' and TransportationStatus le '0006'"]
                if since and mode == ExtractionMode.INCREMENTAL:
                    filters.append(f"LastChangeDateTime ge datetime'{since.isoformat()}'")
                raw = await self._odata_extractor._fetch_entity_set(
                    "API_FREIGHT_ORDER",
                    "A_FreightOrder",
                    filters=filters,
                    max_records=500,
                )
                records = self._map_exceptions_odata(raw)

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
        decision_id = metadata.get("id", 0) if metadata else 0

        if not self._connector:
            return InjectionResult(
                decision_id=decision_id,
                decision_type="load_plan",
                success=False,
                error="Load plan injection requires an RFC connection (BAPI_SHIPMENT_CHANGE)",
            )

        try:
            # BAPI_SHIPMENT_CHANGE accepts a DELIVERIES table where each row
            # declares a delivery (LIKP document number) to attach to the
            # freight order. Action 'I' = insert, 'D' = delete. We always
            # insert — caller is responsible for detaching from the prior
            # freight order in a separate decision if needed.
            deliveries = [
                {"VBELN": str(sid), "POSNR": "000000", "MAFLAG": "I"}
                for sid in shipment_ids
            ]

            header_data: Dict[str, Any] = {"SHIPMENT_NUM": load_external_id}
            header_x: Dict[str, Any] = {"SHIPMENT_NUM": "X"}
            if equipment_type:
                # VSART carries the SAP shipping type — customer-specific
                # mapping from our equipment_type (e.g. "53_DRY_VAN") to SAP
                # VSART ("01") must live in the tenant config, not here.
                header_data["SHIPPING_TYPE"] = equipment_type
                header_x["SHIPPING_TYPE"] = "X"

            result = self._connector.execute_bapi(
                "BAPI_SHIPMENT_CHANGE",
                HEADERDATA=header_data,
                HEADERDATAX=header_x,
                DELIVERIES=deliveries,
            )

            returns = result.get("RETURN", []) or []
            errors = [r for r in returns if r.get("TYPE") in ("E", "A")]
            if errors:
                return InjectionResult(
                    decision_id=decision_id,
                    decision_type="load_plan",
                    success=False,
                    external_id=load_external_id,
                    error="; ".join(
                        r.get("MESSAGE", "") for r in errors
                    ),
                    response=result,
                )

            # Commit — SAP BAPI changes require explicit commit work.
            self._connector.execute_bapi("BAPI_TRANSACTION_COMMIT", WAIT="X")

            return InjectionResult(
                decision_id=decision_id,
                decision_type="load_plan",
                success=True,
                external_id=load_external_id,
                response=result,
            )
        except Exception as e:
            logger.error(f"SAP TM load plan injection failed: {e}")
            return InjectionResult(
                decision_id=decision_id,
                decision_type="load_plan",
                success=False,
                external_id=load_external_id,
                error=str(e),
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

    def _map_freight_units_odata(self, raw: List[Dict]) -> List[Dict[str, Any]]:
        """Map OData A_FreightUnit response to TMS Load dicts."""
        records = []
        for item in raw:
            records.append({
                "shipment_number": item.get("FreightUnit", ""),
                "external_id": item.get("FreightUnit", ""),
                "leg_sequence": item.get("FreightUnitItem", 0),
                "transport_mode": self._map_sap_mode(item.get("TransportationMode", "")),
                "carrier_vendor_number": item.get("Carrier", ""),
                "origin_plant": item.get("SourceLocation", ""),
                "destination_plant": item.get("DestinationLocation", ""),
                "weight": item.get("GrossWeight"),
                "volume": item.get("GrossVolume"),
                "source": "SAP_TM",
            })
        return records

    def _map_carriers_odata(self, raw: List[Dict]) -> List[Dict[str, Any]]:
        """Map OData A_BusinessPartner response to TMS Carrier dicts."""
        records = []
        for item in raw:
            records.append({
                "vendor_number": item.get("BusinessPartner", ""),
                "name": item.get("BusinessPartnerFullName", "")
                        or item.get("OrganizationBPName1", ""),
                "country": item.get("Country", ""),
                "scac": item.get("StandardCarrierAlphaCode") or None,
                "phone": item.get("PhoneNumber1") or None,
                "is_blocked": bool(item.get("BusinessPartnerIsBlocked", False)),
                "is_deleted": bool(item.get("IsMarkedForArchiving", False)),
                "account_group": item.get("BusinessPartnerGrouping", ""),
                "source": "SAP_TM",
            })
        return records

    def _map_exceptions_odata(self, raw: List[Dict]) -> List[Dict[str, Any]]:
        """Map exception-status freight orders from OData to TMS exceptions."""
        status_map = {"0004": "DELAY", "0005": "DAMAGE", "0006": "EXCEPTION"}
        records = []
        for item in raw:
            status = str(item.get("TransportationStatus", "")).strip()
            records.append({
                "shipment_number": item.get("FreightOrder", ""),
                "exception_type": status_map.get(status, "EXCEPTION"),
                "severity": "HIGH",
                "carrier_vendor_number": item.get("Carrier", ""),
                "detected_at": item.get("LastChangeDateTime"),
                "source": "SAP_TM",
            })
        return records

    def _derive_appointments(self, row) -> List[Dict[str, Any]]:
        """Split a VTTK row into pickup + delivery appointment records."""
        tknum = str(row.get("TKNUM", "")).strip()
        carrier = str(row.get("TDLNR", "")).strip()
        appts = []
        planned_pickup = self._parse_sap_datetime(row.get("DTABF"), row.get("UZABF"))
        actual_pickup = self._parse_sap_date(row.get("DTEFB"))
        if planned_pickup or actual_pickup:
            appts.append({
                "shipment_number": tknum,
                "external_id": f"{tknum}-PU",
                "appointment_type": "PICKUP",
                "facility": str(row.get("ABFER", "")).strip(),
                "planned_start": planned_pickup,
                "actual_start": actual_pickup,
                "carrier_vendor_number": carrier,
                "source": "SAP_TM",
            })
        planned_delivery = self._parse_sap_datetime(row.get("DTANK"), row.get("UZANK"))
        actual_delivery = self._parse_sap_date(row.get("DTEFA"))
        if planned_delivery or actual_delivery:
            appts.append({
                "shipment_number": tknum,
                "external_id": f"{tknum}-DL",
                "appointment_type": "DELIVERY",
                "facility": str(row.get("EZESSION", "")).strip(),
                "planned_start": planned_delivery,
                "actual_start": actual_delivery,
                "carrier_vendor_number": carrier,
                "source": "SAP_TM",
            })
        return appts

    def _derive_appointments_odata(self, item: Dict) -> List[Dict[str, Any]]:
        """OData equivalent of _derive_appointments — 2 records per freight order."""
        fo = item.get("FreightOrder", "")
        carrier = item.get("Carrier", "")
        appts = []
        if item.get("PlannedPickUpDateTime") or item.get("ActualPickUpDateTime"):
            appts.append({
                "shipment_number": fo,
                "external_id": f"{fo}-PU",
                "appointment_type": "PICKUP",
                "facility": item.get("SourceLocation", ""),
                "planned_start": item.get("PlannedPickUpDateTime"),
                "actual_start": item.get("ActualPickUpDateTime"),
                "carrier_vendor_number": carrier,
                "source": "SAP_TM",
            })
        if item.get("PlannedDeliveryDateTime") or item.get("ActualDeliveryDateTime"):
            appts.append({
                "shipment_number": fo,
                "external_id": f"{fo}-DL",
                "appointment_type": "DELIVERY",
                "facility": item.get("DestinationLocation", ""),
                "planned_start": item.get("PlannedDeliveryDateTime"),
                "actual_start": item.get("ActualDeliveryDateTime"),
                "carrier_vendor_number": carrier,
                "source": "SAP_TM",
            })
        return appts

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

    # ── CSV Extraction Methods ──────────────────────────────────────────
    # Base S/4HANA (no TM module) uses LIKP/LIPS for deliveries, T001W for
    # plants, LFA1 for vendors/carriers, KNA1 for customers, MARA/MAKT for
    # materials. These map differently from VTTK/VTTS freight orders.

    def _extract_shipments_from_csv(self, since, mode) -> List[Dict[str, Any]]:
        """Extract deliveries from LIKP/LIPS CSVs → TMS shipment records."""
        import pandas as pd
        likp = self._csv_loader.load_table("LIKP")
        lips = self._csv_loader.load_table("LIPS")
        if likp is None or likp.empty:
            logger.warning("LIKP CSV not found or empty")
            return []

        records = []
        for _, row in likp.iterrows():
            ship_date = self._parse_sap_date(row.get("WADAT_IST") or row.get("WADAT"))
            delivery_date = self._parse_sap_date(row.get("LFDAT"))
            actual_gi = self._parse_sap_date(row.get("WADAT_IST"))

            # Get delivery items for weight/volume
            vbeln = str(row.get("VBELN", "")).strip()
            items = lips[lips["VBELN"].astype(str).str.strip() == vbeln] if lips is not None and not lips.empty else pd.DataFrame()
            total_weight = items["BRGEW"].astype(float).sum() if "BRGEW" in items.columns else 0
            total_volume = items["VOLUM"].astype(float).sum() if "VOLUM" in items.columns else 0

            records.append({
                "shipment_number": vbeln,
                "status": "DELIVERED" if actual_gi else "PLANNED",
                # LIKP uses VSTEL (shipping point), not WERKS. VSTEL maps to plant.
                "origin_plant": str(row.get("VSTEL") or row.get("WERKS", "")).strip(),
                "destination_customer": str(row.get("KUNNR", "")).strip(),
                "ship_date": ship_date,
                "planned_delivery_date": delivery_date,
                "actual_delivery_date": actual_gi,
                "total_weight": total_weight,
                "weight_uom": str(row.get("GEWEI", "KG")).strip(),
                "total_volume": total_volume,
                "volume_uom": str(row.get("VOLEH", "M3")).strip(),
                "carrier_vendor": str(row.get("ROUTE", "")).strip(),
                "shipping_type": str(row.get("VSART", "")).strip(),
                "items": [
                    {
                        "material": str(item.get("MATNR", "")).strip(),
                        "quantity": float(item.get("LFIMG", 0)),
                        "uom": str(item.get("MEINS", "EA")).strip(),
                        "weight": float(item.get("BRGEW", 0)),
                    }
                    for _, item in items.iterrows()
                ],
                "_source": "csv",
                "_table": "LIKP",
            })
        logger.info(f"CSV: extracted {len(records)} deliveries from LIKP")
        return records

    def _extract_sites_from_csv(self) -> List[Dict[str, Any]]:
        """Extract plants from T001W + addresses from ADRC → TMS sites."""
        t001w = self._csv_loader.load_table("T001W")
        adrc = self._csv_loader.load_table("ADRC")
        kna1 = self._csv_loader.load_table("KNA1")
        records = []

        if t001w is not None and not t001w.empty:
            for _, row in t001w.iterrows():
                plant = str(row.get("WERKS", "")).strip()
                records.append({
                    "site_code": plant,
                    "name": str(row.get("NAME1", plant)).strip(),
                    "type": "MANUFACTURER",
                    "country": str(row.get("LAND1", "")).strip(),
                    "city": str(row.get("ORT01", "")).strip(),
                    "_source": "csv", "_table": "T001W",
                })

        if kna1 is not None and not kna1.empty:
            for _, row in kna1.iterrows():
                customer = str(row.get("KUNNR", "")).strip()
                records.append({
                    "site_code": f"CUST_{customer}",
                    "name": str(row.get("NAME1", customer)).strip(),
                    "type": "MARKET_DEMAND",
                    "country": str(row.get("LAND1", "")).strip(),
                    "city": str(row.get("ORT01", "")).strip(),
                    "_source": "csv", "_table": "KNA1",
                })

        logger.info(f"CSV: extracted {len(records)} sites (T001W + KNA1)")
        return records

    def _extract_carriers_from_csv(self) -> List[Dict[str, Any]]:
        """Extract vendors with forwarding-agent flag from LFA1 → TMS carriers."""
        lfa1 = self._csv_loader.load_table("LFA1")
        if lfa1 is None or lfa1.empty:
            return []
        records = []
        for _, row in lfa1.iterrows():
            records.append({
                "vendor_number": str(row.get("LIFNR", "")).strip(),
                "name": str(row.get("NAME1", "")).strip(),
                "country": str(row.get("LAND1", "")).strip(),
                "scac": str(row.get("SCAC", "")).strip() if "SCAC" in row.index else "",
                "tax_number_1": str(row.get("STCD1", "")).strip(),
                "phone": str(row.get("TELF1", "")).strip(),
                "_source": "csv", "_table": "LFA1",
            })
        logger.info(f"CSV: extracted {len(records)} vendors from LFA1")
        return records

    def _extract_materials_from_csv(self) -> List[Dict[str, Any]]:
        """Extract materials from MARA/MAKT → TMS commodities."""
        mara = self._csv_loader.load_table("MARA")
        makt = self._csv_loader.load_table("MAKT")
        if mara is None or mara.empty:
            return []
        records = []
        # Build description lookup from MAKT
        desc_map = {}
        if makt is not None and not makt.empty:
            for _, row in makt.iterrows():
                matnr = str(row.get("MATNR", "")).strip()
                desc_map[matnr] = str(row.get("MAKTX", "")).strip()

        for _, row in mara.iterrows():
            matnr = str(row.get("MATNR", "")).strip()
            records.append({
                "material_number": matnr,
                "description": desc_map.get(matnr, matnr),
                "material_type": str(row.get("MTART", "")).strip(),
                "material_group": str(row.get("MATKL", "")).strip(),
                "base_uom": str(row.get("MEINS", "EA")).strip(),
                "gross_weight": float(row.get("BRGEW", 0)) if "BRGEW" in row.index else 0,
                "weight_uom": str(row.get("GEWEI", "KG")).strip() if "GEWEI" in row.index else "KG",
                "volume": float(row.get("VOLUM", 0)) if "VOLUM" in row.index else 0,
                "_source": "csv", "_table": "MARA",
            })
        logger.info(f"CSV: extracted {len(records)} materials from MARA")
        return records
