"""
project44 Webhook Handler

Receives and processes inbound webhook events from project44:
- Tracking status updates (shipment milestones)
- ETA updates with confidence
- Exception/alert notifications
- Geolocation position updates

Flow:
1. Receive HTTP POST from p44 webhook
2. Verify HMAC signature (if configured)
3. Parse event payload
4. Deduplicate against p44_event_id
5. Map to TrackingEvent entity via P44DataMapper
6. Persist event + update Shipment status/ETA
7. Emit internal event for TRM processing

Webhook payload format (p44 v4):
{
    "shipmentId": "uuid",
    "eventType": "TRACKING_UPDATE",
    "event": {
        "eventId": "uuid",
        "type": "IN_TRANSIT",
        "dateTime": "2026-04-09T14:30:00Z",
        "location": { ... },
        "estimateDateTime": "2026-04-10T08:00:00Z"
    },
    "shipmentIdentifiers": [...],
    "carrierIdentifier": { ... }
}
"""

import logging
import hashlib
import hmac
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


# ── p44 Webhook Event Types ────────────────────────────────────────────────
# These are the top-level eventType values p44 sends on webhooks

class P44WebhookEventType:
    """Constants for p44 webhook event types."""
    TRACKING_UPDATE = "TRACKING_UPDATE"
    SHIPMENT_LIFECYCLE = "SHIPMENT_LIFECYCLE"
    ETA_UPDATE = "ETA_UPDATE"
    EXCEPTION = "EXCEPTION"
    POSITION_UPDATE = "POSITION_UPDATE"
    INFO_UPDATE = "INFO_UPDATE"
    # Ocean-specific
    VESSEL_UPDATE = "VESSEL_UPDATE"
    PORT_EVENT = "PORT_EVENT"
    CONTAINER_EVENT = "CONTAINER_EVENT"


# ── p44 Event Type → TMS TrackingEventType Mapping ─────────────────────────

P44_EVENT_TYPE_MAP = {
    # Movement
    "PICKED_UP": "PICKED_UP",
    "DEPARTED": "DEPARTED",
    "IN_TRANSIT": "IN_TRANSIT",
    "ARRIVAL_AT_STOP": "ARRIVAL_AT_STOP",
    "DEPARTED_STOP": "DEPARTED_STOP",
    "OUT_FOR_DELIVERY": "OUT_FOR_DELIVERY",
    "DELIVERED": "DELIVERED",
    # Terminal (LTL)
    "ARRIVED_AT_TERMINAL": "ARRIVED_AT_TERMINAL",
    "DEPARTED_TERMINAL": "DEPARTED_TERMINAL",
    # Ocean
    "VESSEL_DEPARTED": "VESSEL_DEPARTED",
    "VESSEL_ARRIVED": "VESSEL_ARRIVED",
    "LOADED_ON_VESSEL": "LOADED_ON_VESSEL",
    "DISCHARGED": "DISCHARGED",
    "GATE_IN": "GATE_IN",
    "GATE_OUT": "GATE_OUT",
    "TRANSSHIPMENT": "TRANSSHIPMENT",
    "CUSTOMS_CLEARED": "CUSTOMS_CLEARED",
    "CUSTOMS_HOLD": "CUSTOMS_HOLD",
    # Intermodal
    "RAIL_DEPARTED": "RAIL_DEPARTED",
    "RAIL_ARRIVED": "RAIL_ARRIVED",
    # Administrative
    "CREATED": "CREATED",
    "UPDATED": "UPDATED",
    "CANCELLED": "CANCELLED",
    # Appointment
    "APPOINTMENT_SET": "APPOINTMENT_SET",
    "UPDATED_DELIVERY_APPT": "UPDATED_DELIVERY_APPT",
    # Exceptions
    "DELAYED": "DELAYED",
    "EXCEPTION": "EXCEPTION",
    "RETURNED": "RETURNED",
    # ETA
    "ETA_UPDATED": "ETA_UPDATED",
    "ETA_CHANGE": "ETA_UPDATED",
}

# ── p44 Event Type → Shipment Status Mapping ──────────────────────────────
# Which p44 events should trigger a shipment status transition

P44_STATUS_TRANSITION_MAP = {
    "PICKED_UP": "IN_TRANSIT",
    "DEPARTED": "IN_TRANSIT",
    "IN_TRANSIT": "IN_TRANSIT",
    "ARRIVAL_AT_STOP": "AT_STOP",
    "DEPARTED_STOP": "IN_TRANSIT",
    "OUT_FOR_DELIVERY": "OUT_FOR_DELIVERY",
    "DELIVERED": "DELIVERED",
    "CANCELLED": "CANCELLED",
    "EXCEPTION": "EXCEPTION",
    # Ocean milestones — keep in-transit
    "VESSEL_DEPARTED": "IN_TRANSIT",
    "VESSEL_ARRIVED": "IN_TRANSIT",
    "LOADED_ON_VESSEL": "IN_TRANSIT",
    "DISCHARGED": "IN_TRANSIT",
    "GATE_OUT": "IN_TRANSIT",
}

# ── p44 Exception Code → TMS ExceptionType Mapping ────────────────────────

P44_EXCEPTION_MAP = {
    "LATE_PICKUP": "LATE_PICKUP",
    "MISSED_PICKUP": "MISSED_PICKUP",
    "LATE_DELIVERY": "LATE_DELIVERY",
    "MISSED_DELIVERY": "MISSED_DELIVERY",
    "ROUTE_DEVIATION": "ROUTE_DEVIATION",
    "TEMPERATURE_EXCURSION": "TEMPERATURE_EXCURSION",
    "DAMAGE": "DAMAGE",
    "SHORTAGE": "SHORTAGE",
    "OVERAGE": "OVERAGE",
    "REFUSED": "REFUSED",
    "ROLLED": "ROLLED_CONTAINER",
    "ROLLED_CONTAINER": "ROLLED_CONTAINER",
    "PORT_CONGESTION": "PORT_CONGESTION",
    "CUSTOMS_HOLD": "CUSTOMS_HOLD",
    "WEATHER": "WEATHER_DELAY",
    "WEATHER_DELAY": "WEATHER_DELAY",
    "BREAKDOWN": "CARRIER_BREAKDOWN",
    "CARRIER_BREAKDOWN": "CARRIER_BREAKDOWN",
    "DETENTION": "DETENTION",
    "DEMURRAGE": "DEMURRAGE",
}


class P44WebhookHandler:
    """
    Processes inbound project44 webhook events.

    Responsibilities:
    - Signature verification (HMAC-SHA256)
    - Payload parsing and normalization
    - Event deduplication via p44_event_id
    - Tracking event creation
    - Shipment status/ETA updates
    - Exception detection and creation

    Usage:
        handler = P44WebhookHandler(webhook_secret="your-secret")
        result = await handler.process_webhook(headers, body, tenant_id, db_session)
    """

    def __init__(self, webhook_secret: str = ""):
        self.webhook_secret = webhook_secret

    # ── Signature Verification ──────────────────────────────────────────

    def verify_signature(
        self,
        payload_bytes: bytes,
        signature_header: str,
    ) -> bool:
        """
        Verify p44 webhook HMAC-SHA256 signature.

        Args:
            payload_bytes: Raw request body bytes
            signature_header: Value of X-P44-Signature header

        Returns:
            True if signature is valid or verification is disabled
        """
        if not self.webhook_secret:
            logger.warning("P44 webhook signature verification disabled (no secret configured)")
            return True

        if not signature_header:
            logger.warning("P44 webhook missing signature header")
            return False

        expected = hmac.new(
            self.webhook_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        is_valid = hmac.compare_digest(expected, signature_header)
        if not is_valid:
            logger.warning("P44 webhook signature mismatch")
        return is_valid

    # ── Main Processing Pipeline ────────────────────────────────────────

    async def process_webhook(
        self,
        headers: Dict[str, str],
        body: bytes,
        tenant_id: int,
        db_session: Any,
    ) -> Dict[str, Any]:
        """
        Process a single p44 webhook delivery.

        Args:
            headers: HTTP request headers
            body: Raw request body bytes
            tenant_id: Tenant that owns this p44 integration
            db_session: SQLAlchemy AsyncSession

        Returns:
            Processing result dict with status and any created entities
        """
        # 1. Verify signature
        signature = headers.get("x-p44-signature", headers.get("X-P44-Signature", ""))
        if not self.verify_signature(body, signature):
            return {"status": "rejected", "reason": "invalid_signature"}

        # 2. Parse payload
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as e:
            logger.error(f"P44 webhook: invalid JSON — {e}")
            return {"status": "rejected", "reason": "invalid_json"}

        # 3. Extract top-level fields
        webhook_event_type = payload.get("eventType", "TRACKING_UPDATE")
        p44_shipment_id = payload.get("shipmentId")
        event_data = payload.get("event", {})
        p44_event_id = event_data.get("eventId")
        shipment_identifiers = payload.get("shipmentIdentifiers", [])
        carrier_identifier = payload.get("carrierIdentifier", {})

        logger.info(
            f"P44 webhook: type={webhook_event_type}, "
            f"shipment={p44_shipment_id}, event_id={p44_event_id}"
        )

        # 4. Resolve internal shipment
        shipment = await self._resolve_shipment(
            p44_shipment_id, shipment_identifiers, tenant_id, db_session
        )
        if not shipment:
            logger.warning(
                f"P44 webhook: could not resolve shipment for "
                f"p44_id={p44_shipment_id}, identifiers={shipment_identifiers}"
            )
            return {
                "status": "unmatched",
                "reason": "shipment_not_found",
                "p44_shipment_id": p44_shipment_id,
            }

        # 5. Deduplicate
        if p44_event_id:
            is_dup = await self._is_duplicate_event(p44_event_id, db_session)
            if is_dup:
                logger.info(f"P44 webhook: duplicate event {p44_event_id}, skipping")
                return {"status": "duplicate", "p44_event_id": p44_event_id}

        # 6. Process based on webhook event type
        result = {"status": "processed", "p44_shipment_id": p44_shipment_id}

        if webhook_event_type in (
            P44WebhookEventType.TRACKING_UPDATE,
            P44WebhookEventType.SHIPMENT_LIFECYCLE,
            P44WebhookEventType.POSITION_UPDATE,
            P44WebhookEventType.VESSEL_UPDATE,
            P44WebhookEventType.PORT_EVENT,
            P44WebhookEventType.CONTAINER_EVENT,
        ):
            tracking_event = await self._process_tracking_event(
                shipment, event_data, payload, tenant_id, db_session
            )
            if tracking_event:
                result["tracking_event_id"] = tracking_event.get("id")

        elif webhook_event_type == P44WebhookEventType.ETA_UPDATE:
            await self._process_eta_update(
                shipment, event_data, tenant_id, db_session
            )
            result["eta_updated"] = True

        elif webhook_event_type == P44WebhookEventType.EXCEPTION:
            exception = await self._process_exception(
                shipment, event_data, payload, tenant_id, db_session
            )
            if exception:
                result["exception_id"] = exception.get("id")

        # 7. Update shipment status if warranted
        await self._update_shipment_status(
            shipment, event_data, db_session
        )

        return result

    # ── Shipment Resolution ─────────────────────────────────────────────

    async def _resolve_shipment(
        self,
        p44_shipment_id: Optional[str],
        identifiers: List[Dict],
        tenant_id: int,
        db_session: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve p44 webhook to internal Shipment.

        Strategy (in priority order):
        1. Match by p44_shipment_id on Shipment
        2. Match by shipment identifiers (BOL, PO, etc.)
        3. Match by shipment_number
        """
        from sqlalchemy import select, and_

        # Strategy 1: Direct p44 ID match
        if p44_shipment_id:
            from ...models.tms_entities import Shipment
            stmt = select(Shipment).where(
                and_(
                    Shipment.tenant_id == tenant_id,
                    Shipment.p44_shipment_id == p44_shipment_id,
                )
            )
            result = await db_session.execute(stmt)
            shipment = result.scalar_one_or_none()
            if shipment:
                return self._shipment_to_dict(shipment)

        # Strategy 2: Match via ShipmentIdentifier table
        if identifiers:
            from ...models.tms_entities import ShipmentIdentifier, Shipment
            for ident in identifiers:
                ident_type = ident.get("type")
                ident_value = ident.get("value")
                if not ident_type or not ident_value:
                    continue

                stmt = (
                    select(Shipment)
                    .join(ShipmentIdentifier, ShipmentIdentifier.shipment_id == Shipment.id)
                    .where(
                        and_(
                            ShipmentIdentifier.tenant_id == tenant_id,
                            ShipmentIdentifier.identifier_type == ident_type,
                            ShipmentIdentifier.identifier_value == ident_value,
                        )
                    )
                )
                result = await db_session.execute(stmt)
                shipment = result.scalar_one_or_none()
                if shipment:
                    # Backfill p44_shipment_id if we matched by identifier
                    if p44_shipment_id and not shipment.p44_shipment_id:
                        shipment.p44_shipment_id = p44_shipment_id
                        await db_session.flush()
                    return self._shipment_to_dict(shipment)

        return None

    def _shipment_to_dict(self, shipment: Any) -> Dict[str, Any]:
        """Convert Shipment ORM object to minimal dict for processing."""
        return {
            "id": shipment.id,
            "shipment_number": shipment.shipment_number,
            "status": shipment.status.value if hasattr(shipment.status, 'value') else shipment.status,
            "p44_shipment_id": shipment.p44_shipment_id,
            "tenant_id": shipment.tenant_id,
        }

    # ── Deduplication ───────────────────────────────────────────────────

    async def _is_duplicate_event(
        self,
        p44_event_id: str,
        db_session: Any,
    ) -> bool:
        """Check if we've already processed this p44 event."""
        from sqlalchemy import select, func
        from ...models.tms_entities import TrackingEvent

        stmt = select(func.count()).where(
            TrackingEvent.p44_event_id == p44_event_id
        )
        result = await db_session.execute(stmt)
        count = result.scalar()
        return count > 0

    # ── Tracking Event Processing ───────────────────────────────────────

    async def _process_tracking_event(
        self,
        shipment: Dict[str, Any],
        event_data: Dict[str, Any],
        full_payload: Dict[str, Any],
        tenant_id: int,
        db_session: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a TrackingEvent from p44 webhook event data.

        Returns dict with created event ID or None.
        """
        from ...models.tms_entities import TrackingEvent, TrackingEventType

        # Map p44 event type to TMS enum
        p44_type = event_data.get("type", "UPDATED")
        tms_type_str = P44_EVENT_TYPE_MAP.get(p44_type, "UPDATED")
        try:
            event_type = TrackingEventType(tms_type_str)
        except ValueError:
            logger.warning(f"P44 webhook: unknown event type '{p44_type}', defaulting to UPDATED")
            event_type = TrackingEventType.UPDATED

        # Parse event timestamp
        event_ts = self._parse_datetime(event_data.get("dateTime"))
        if not event_ts:
            event_ts = datetime.utcnow()

        # Extract location
        location = event_data.get("location", {})
        address = location.get("address", {})
        coordinates = location.get("coordinates", {})

        # Extract ocean-specific fields
        vessel = event_data.get("vessel", {})
        container = event_data.get("container", {})

        # Extract equipment
        equipment = event_data.get("equipmentIdentifier", {})

        # Extract temperature
        temp_data = event_data.get("temperature", {})

        # Build tracking event
        tracking_event = TrackingEvent(
            shipment_id=shipment["id"],
            event_type=event_type,
            event_timestamp=event_ts,
            received_timestamp=datetime.utcnow(),
            # p44 identifiers
            p44_event_id=event_data.get("eventId"),
            p44_shipment_id=full_payload.get("shipmentId"),
            p44_shipment_leg_id=event_data.get("shipmentLegId"),
            # Location
            location_name=location.get("name"),
            address_line_1=address.get("addressLine1"),
            city=address.get("city"),
            state=address.get("state"),
            postal_code=address.get("postalCode"),
            country=address.get("country"),
            latitude=coordinates.get("latitude"),
            longitude=coordinates.get("longitude"),
            # Status
            status_code=event_data.get("statusCode"),
            status_description=event_data.get("description"),
            # ETA
            estimated_arrival=self._parse_datetime(event_data.get("estimateDateTime")),
            estimated_departure=self._parse_datetime(event_data.get("estimateDepartureDateTime")),
            # Stop reference
            stop_sequence=event_data.get("stopSequence"),
            stop_type=event_data.get("stopType"),
            # Ocean
            vessel_name=vessel.get("name"),
            voyage_number=vessel.get("voyageNumber"),
            vessel_imo=vessel.get("imo"),
            port_locode=event_data.get("portLocode"),
            container_number=container.get("number") or event_data.get("containerNumber"),
            seal_number=container.get("sealNumber"),
            # Equipment
            equipment_identifier_type=equipment.get("type"),
            equipment_identifier_value=equipment.get("value"),
            # Temperature
            temperature=temp_data.get("value"),
            temperature_uom=temp_data.get("unit", "F"),
            temperature_set_point=temp_data.get("setPoint"),
            # Exception
            exception_code=event_data.get("exceptionCode"),
            exception_description=event_data.get("exceptionDescription"),
            # Source
            source="P44",
            raw_payload=full_payload,
            # Tenant
            tenant_id=tenant_id,
        )

        db_session.add(tracking_event)
        await db_session.flush()

        logger.info(
            f"P44 webhook: created TrackingEvent {tracking_event.id} "
            f"(type={event_type.value}) for shipment {shipment['shipment_number']}"
        )

        return {"id": tracking_event.id, "event_type": event_type.value}

    # ── ETA Update Processing ───────────────────────────────────────────

    async def _process_eta_update(
        self,
        shipment: Dict[str, Any],
        event_data: Dict[str, Any],
        tenant_id: int,
        db_session: Any,
    ) -> None:
        """
        Update Shipment ETA from p44 ETA event.

        p44 ETA events include:
        - estimateDateTime (point estimate)
        - estimateWindow.start / .end (range)
        - confidence (HIGH, MEDIUM, LOW)
        """
        from ...models.tms_entities import Shipment

        eta_dt = self._parse_datetime(event_data.get("estimateDateTime"))
        if not eta_dt:
            return

        stmt_select = await db_session.get(Shipment, shipment["id"])
        if not stmt_select:
            return

        ship = stmt_select
        ship.estimated_arrival = eta_dt
        ship.last_tracking_update = datetime.utcnow()

        # Build confidence interval from p44 window if available
        eta_window = event_data.get("estimateWindow", {})
        if eta_window:
            ship.eta_confidence = {
                "p10": eta_window.get("start"),
                "p50": event_data.get("estimateDateTime"),
                "p90": eta_window.get("end"),
                "source": "P44",
                "confidence": event_data.get("confidence", "MEDIUM"),
                "updated_at": datetime.utcnow().isoformat(),
            }

        await db_session.flush()
        logger.info(
            f"P44 webhook: updated ETA for shipment {shipment['shipment_number']} → {eta_dt}"
        )

    # ── Exception Processing ────────────────────────────────────────────

    async def _process_exception(
        self,
        shipment: Dict[str, Any],
        event_data: Dict[str, Any],
        full_payload: Dict[str, Any],
        tenant_id: int,
        db_session: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a ShipmentException from p44 exception event.

        Also creates a tracking event for the exception.
        """
        from ...models.tms_entities import (
            ShipmentException,
            ExceptionType,
            ExceptionSeverity,
        )

        # Map p44 exception code to TMS enum
        p44_code = event_data.get("exceptionCode", event_data.get("type", ""))
        tms_code = P44_EXCEPTION_MAP.get(p44_code)
        if not tms_code:
            # Fallback: create tracking event only
            logger.info(f"P44 webhook: unmapped exception code '{p44_code}', creating tracking event only")
            await self._process_tracking_event(shipment, event_data, full_payload, tenant_id, db_session)
            return None

        try:
            exception_type = ExceptionType(tms_code)
        except ValueError:
            logger.warning(f"P44 webhook: invalid exception type '{tms_code}'")
            return None

        # Determine severity from p44 data
        severity = self._map_severity(event_data.get("severity", "MEDIUM"))

        # Extract location
        location = event_data.get("location", {})
        coordinates = location.get("coordinates", {})

        exception = ShipmentException(
            shipment_id=shipment["id"],
            exception_type=exception_type,
            severity=severity,
            description=event_data.get("description", f"p44 exception: {p44_code}"),
            detected_at=self._parse_datetime(event_data.get("dateTime")) or datetime.utcnow(),
            estimated_delay_hrs=event_data.get("estimatedDelayHours"),
            detection_source="P44",
            detection_event_id=event_data.get("eventId"),
            exception_lat=coordinates.get("latitude"),
            exception_lon=coordinates.get("longitude"),
            exception_location_desc=location.get("name"),
            tenant_id=tenant_id,
        )

        db_session.add(exception)
        await db_session.flush()

        # Also create a tracking event for the exception
        event_data_copy = dict(event_data)
        if "type" not in event_data_copy:
            event_data_copy["type"] = "EXCEPTION"
        await self._process_tracking_event(
            shipment, event_data_copy, full_payload, tenant_id, db_session
        )

        logger.info(
            f"P44 webhook: created ShipmentException {exception.id} "
            f"(type={exception_type.value}, severity={severity.value}) "
            f"for shipment {shipment['shipment_number']}"
        )

        return {"id": exception.id, "type": exception_type.value}

    # ── Shipment Status Update ──────────────────────────────────────────

    async def _update_shipment_status(
        self,
        shipment: Dict[str, Any],
        event_data: Dict[str, Any],
        db_session: Any,
    ) -> None:
        """
        Update shipment status based on tracking event type.

        Only transitions to later lifecycle states (no backward transitions
        except for EXCEPTION).
        """
        from ...models.tms_entities import Shipment, ShipmentStatus

        p44_type = event_data.get("type", "")
        new_status_str = P44_STATUS_TRANSITION_MAP.get(p44_type)
        if not new_status_str:
            return

        try:
            new_status = ShipmentStatus(new_status_str)
        except ValueError:
            return

        # Define valid forward transitions
        status_order = [
            ShipmentStatus.DRAFT,
            ShipmentStatus.TENDERED,
            ShipmentStatus.ACCEPTED,
            ShipmentStatus.DECLINED,
            ShipmentStatus.DISPATCHED,
            ShipmentStatus.IN_TRANSIT,
            ShipmentStatus.AT_STOP,
            ShipmentStatus.OUT_FOR_DELIVERY,
            ShipmentStatus.DELIVERED,
            ShipmentStatus.POD_RECEIVED,
            ShipmentStatus.INVOICED,
            ShipmentStatus.CLOSED,
        ]

        current_status_str = shipment["status"]
        try:
            current_status = ShipmentStatus(current_status_str)
        except ValueError:
            return

        # Allow forward transitions + EXCEPTION/CANCELLED at any time
        is_forward = (
            new_status in (ShipmentStatus.EXCEPTION, ShipmentStatus.CANCELLED)
            or (
                new_status in status_order
                and current_status in status_order
                and status_order.index(new_status) > status_order.index(current_status)
            )
            # Allow AT_STOP ↔ IN_TRANSIT cycling for multi-stop shipments
            or (
                current_status == ShipmentStatus.AT_STOP
                and new_status == ShipmentStatus.IN_TRANSIT
            )
        )

        if not is_forward:
            return

        ship = await db_session.get(Shipment, shipment["id"])
        if not ship:
            return

        old_status = ship.status
        ship.status = new_status
        ship.last_tracking_update = datetime.utcnow()

        # Update position if available
        location = event_data.get("location", {})
        coords = location.get("coordinates", {})
        if coords.get("latitude") and coords.get("longitude"):
            ship.current_lat = coords["latitude"]
            ship.current_lon = coords["longitude"]

        # Update actual dates on milestones
        event_ts = self._parse_datetime(event_data.get("dateTime"))
        if event_ts:
            if new_status == ShipmentStatus.IN_TRANSIT and not ship.actual_pickup_date:
                ship.actual_pickup_date = event_ts
            elif new_status == ShipmentStatus.DELIVERED:
                ship.actual_delivery_date = event_ts

        await db_session.flush()

        logger.info(
            f"P44 webhook: shipment {shipment['shipment_number']} "
            f"status {old_status} → {new_status.value}"
        )

    # ── Batch Webhook Processing ────────────────────────────────────────

    async def process_webhook_batch(
        self,
        events: List[Tuple[Dict[str, str], bytes]],
        tenant_id: int,
        db_session: Any,
    ) -> List[Dict[str, Any]]:
        """
        Process multiple webhook deliveries in sequence.

        Used for catching up on missed webhooks (p44 retry queue).

        Args:
            events: List of (headers, body) tuples
            tenant_id: Tenant ID
            db_session: SQLAlchemy AsyncSession

        Returns:
            List of processing results
        """
        results = []
        for headers, body in events:
            try:
                result = await self.process_webhook(headers, body, tenant_id, db_session)
                results.append(result)
            except Exception as e:
                logger.error(f"P44 webhook batch error: {e}")
                results.append({"status": "error", "reason": str(e)})
        return results

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
        """Parse ISO 8601 datetime string from p44."""
        if not value:
            return None
        try:
            # Handle Z suffix and +00:00 timezone
            cleaned = value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(cleaned)
            # Store as naive UTC
            return dt.replace(tzinfo=None)
        except (ValueError, TypeError):
            logger.warning(f"P44 webhook: could not parse datetime '{value}'")
            return None

    @staticmethod
    def _map_severity(p44_severity: str) -> "ExceptionSeverity":
        """Map p44 severity string to TMS ExceptionSeverity enum."""
        from ...models.tms_entities import ExceptionSeverity

        mapping = {
            "LOW": ExceptionSeverity.LOW,
            "MEDIUM": ExceptionSeverity.MEDIUM,
            "HIGH": ExceptionSeverity.HIGH,
            "CRITICAL": ExceptionSeverity.CRITICAL,
            "WARNING": ExceptionSeverity.MEDIUM,
            "INFO": ExceptionSeverity.LOW,
            "SEVERE": ExceptionSeverity.CRITICAL,
        }
        return mapping.get(p44_severity.upper(), ExceptionSeverity.MEDIUM)
