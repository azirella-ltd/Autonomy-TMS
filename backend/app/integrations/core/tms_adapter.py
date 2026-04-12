"""
Abstract TMS Extraction/Injection Adapter

Base class for integrating with external TMS systems (SAP TM, Oracle OTM,
Blue Yonder, Manhattan Active TM, MercuryGate). Each vendor implements
this interface against their specific API/protocol.

The adapter handles two directions:
- Extraction (inbound): read shipments, loads, carriers, rates, appointments,
  exceptions from the external TMS into Autonomy's canonical entities
- Injection (outbound): push AIIO-governed decisions back to the external TMS

See docs/TMS_ERP_INTEGRATION.md for the full architecture.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ExtractionMode(str, Enum):
    """How data should be extracted."""
    FULL = "full"          # Full extraction (initial load or periodic refresh)
    INCREMENTAL = "incremental"  # Only records changed since last sync
    HISTORICAL = "historical"    # Bulk historical extraction for ML training


@dataclass
class ExtractionResult:
    """Result of an extraction operation."""
    entity_type: str           # "shipments", "loads", "carriers", etc.
    records_extracted: int
    records_mapped: int        # Successfully mapped to canonical entities
    records_skipped: int       # Skipped (validation failures, duplicates)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    duration_seconds: float = 0.0
    watermark: Optional[str] = None  # For incremental: the "since" marker for next run


@dataclass
class InjectionResult:
    """Result of pushing a decision back to the external TMS."""
    decision_id: int
    decision_type: str
    success: bool
    external_id: Optional[str] = None  # ID assigned by the external TMS
    error: Optional[str] = None
    response: Optional[Dict[str, Any]] = None


@dataclass
class ConnectionConfig:
    """Base connection configuration — vendor-specific subclasses add fields."""
    tenant_id: int
    connection_name: str
    base_url: Optional[str] = None
    auth_type: str = "oauth2"
    environment: str = "sandbox"  # "sandbox" or "production"


class TMSExtractionAdapter(ABC):
    """
    Abstract base for TMS-specific data extraction.

    One implementation per TMS vendor (SAPTMAdapter, OracleTMAdapter, etc.).
    Each adapter shares the same interface so Autonomy's ingestion pipeline
    works identically regardless of the source TMS.

    Lifecycle:
        adapter = SAPTMAdapter(config)
        await adapter.connect()
        result = await adapter.extract_shipments(since=last_sync)
        await adapter.disconnect()
    """

    def __init__(self, config: ConnectionConfig):
        self.config = config
        self._connected = False

    # ── Connection Management ────────────────────────────────────────────

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to the external TMS. Returns True on success."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the connection."""
        ...

    @abstractmethod
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test the connection and return status info.

        Returns:
            {"connected": True/False, "version": "...", "message": "...", "latency_ms": N}
        """
        ...

    # ── Extraction (Inbound: External TMS → Autonomy) ───────────────────

    @abstractmethod
    async def extract_shipments(
        self,
        since: Optional[datetime] = None,
        mode: ExtractionMode = ExtractionMode.INCREMENTAL,
        batch_size: int = 500,
    ) -> ExtractionResult:
        """
        Extract shipments from the external TMS.

        Maps to TMS Shipment entity. Includes status, origin/destination,
        carrier assignment, dates, identifiers.
        """
        ...

    @abstractmethod
    async def extract_loads(
        self,
        since: Optional[datetime] = None,
        mode: ExtractionMode = ExtractionMode.INCREMENTAL,
        batch_size: int = 500,
    ) -> ExtractionResult:
        """
        Extract loads (physical groupings on equipment).

        Maps to TMS Load + LoadItem entities. Includes load number,
        equipment type, weight/volume, stop sequence.
        """
        ...

    @abstractmethod
    async def extract_carriers(
        self,
        mode: ExtractionMode = ExtractionMode.FULL,
    ) -> ExtractionResult:
        """
        Extract carrier master data.

        Maps to TMS Carrier entity (extends canonical TradingPartner).
        Includes SCAC, MC#, DOT#, equipment capabilities, insurance,
        service areas.
        """
        ...

    @abstractmethod
    async def extract_rates(
        self,
        mode: ExtractionMode = ExtractionMode.FULL,
    ) -> ExtractionResult:
        """
        Extract freight rates (contract + spot).

        Maps to TMS FreightRate + CarrierContract entities. Includes
        lane, mode, carrier, rate amount, validity period, accessorials.
        """
        ...

    @abstractmethod
    async def extract_appointments(
        self,
        since: Optional[datetime] = None,
        mode: ExtractionMode = ExtractionMode.INCREMENTAL,
    ) -> ExtractionResult:
        """
        Extract dock appointments.

        Maps to TMS Appointment entity. Includes scheduled/actual times,
        dock door, appointment type (pickup/delivery), status.
        """
        ...

    @abstractmethod
    async def extract_exceptions(
        self,
        since: Optional[datetime] = None,
        mode: ExtractionMode = ExtractionMode.INCREMENTAL,
    ) -> ExtractionResult:
        """
        Extract shipment exceptions (delays, damages, refusals).

        Maps to TMS ShipmentException entity. Includes exception type,
        severity, timestamps, resolution status.
        """
        ...

    async def extract_historical(
        self,
        start_date: datetime,
        end_date: datetime,
        entity_types: Optional[List[str]] = None,
        batch_size: int = 1000,
        on_progress: Optional[callable] = None,
    ) -> List[ExtractionResult]:
        """
        Bulk historical extraction for ML training data.

        Extracts 6-24 months of execution data. Larger batches,
        progress reporting, resume-on-failure support.

        Default implementation calls each extract method with HISTORICAL
        mode. Vendor-specific adapters can override for optimized bulk
        extraction (e.g., SAP background jobs, Oracle data export).
        """
        types = entity_types or [
            "shipments", "loads", "carriers", "rates",
            "appointments", "exceptions",
        ]
        results = []
        extractors = {
            "shipments": lambda: self.extract_shipments(since=start_date, mode=ExtractionMode.HISTORICAL, batch_size=batch_size),
            "loads": lambda: self.extract_loads(since=start_date, mode=ExtractionMode.HISTORICAL, batch_size=batch_size),
            "carriers": lambda: self.extract_carriers(mode=ExtractionMode.HISTORICAL),
            "rates": lambda: self.extract_rates(mode=ExtractionMode.HISTORICAL),
            "appointments": lambda: self.extract_appointments(since=start_date, mode=ExtractionMode.HISTORICAL),
            "exceptions": lambda: self.extract_exceptions(since=start_date, mode=ExtractionMode.HISTORICAL),
        }
        for i, entity_type in enumerate(types):
            if entity_type in extractors:
                result = await extractors[entity_type]()
                results.append(result)
                if on_progress:
                    on_progress(entity_type, i + 1, len(types), result)
        return results

    # ── Injection (Outbound: Autonomy → External TMS) ───────────────────

    @abstractmethod
    async def inject_carrier_assignment(
        self,
        shipment_external_id: str,
        carrier_id: str,
        rate: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InjectionResult:
        """
        Push a carrier assignment decision to the external TMS.

        Called when the FreightProcurementTRM assigns a carrier and the
        decision passes AIIO governance (AUTOMATE or INSPECT→approved).
        """
        ...

    @abstractmethod
    async def inject_appointment_change(
        self,
        appointment_external_id: str,
        new_start: datetime,
        new_end: datetime,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InjectionResult:
        """
        Push an appointment reschedule to the external TMS.

        Called when the DockSchedulingTRM optimizes appointment times.
        """
        ...

    @abstractmethod
    async def inject_load_plan(
        self,
        load_external_id: str,
        shipment_ids: List[str],
        equipment_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InjectionResult:
        """
        Push a load consolidation plan to the external TMS.

        Called when the LoadBuildTRM creates or modifies a load.
        """
        ...

    async def inject_decision(
        self,
        decision: Dict[str, Any],
    ) -> InjectionResult:
        """
        Generic decision injection — routes to the type-specific method.

        Override this for vendors that have a single unified decision API
        rather than per-type endpoints.
        """
        decision_type = decision.get("decision_type", "")
        if "carrier" in decision_type or "procurement" in decision_type:
            return await self.inject_carrier_assignment(
                shipment_external_id=decision.get("shipment_external_id", ""),
                carrier_id=decision.get("carrier_id", ""),
                rate=decision.get("rate"),
                metadata=decision,
            )
        elif "appointment" in decision_type or "dock" in decision_type:
            return await self.inject_appointment_change(
                appointment_external_id=decision.get("appointment_external_id", ""),
                new_start=decision.get("new_start"),
                new_end=decision.get("new_end"),
                metadata=decision,
            )
        elif "load" in decision_type:
            return await self.inject_load_plan(
                load_external_id=decision.get("load_external_id", ""),
                shipment_ids=decision.get("shipment_ids", []),
                equipment_type=decision.get("equipment_type"),
                metadata=decision,
            )
        else:
            return InjectionResult(
                decision_id=decision.get("id", 0),
                decision_type=decision_type,
                success=False,
                error=f"Unknown decision type for injection: {decision_type}",
            )
