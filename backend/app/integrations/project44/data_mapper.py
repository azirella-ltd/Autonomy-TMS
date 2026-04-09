"""
project44 Data Mapper

Bidirectional mapping between project44 API v4 schemas and TMS SQLAlchemy entities.

Mappings:
- Shipment ↔ p44 TrackedShipment
- TrackingEvent ↔ p44 TrackedShipmentEvent
- Carrier ↔ p44 CapacityProvider / CarrierIdentifier
- ShipmentIdentifier ↔ p44 shipmentIdentifiers array
- ShipmentLeg ↔ p44 shipmentLegs
- Stop (Site) ↔ p44 stop (with address)

Direction conventions:
- to_p44_*  : TMS entity → p44 API payload (for outbound requests)
- from_p44_* : p44 API response → TMS entity dict (for persistence)

All from_p44_* methods return plain dicts suitable for ORM constructor kwargs.
Caller is responsible for creating/updating ORM objects and session management.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


# ── TransportMode ↔ p44 mode string ────────────────────────────────────────

TMS_TO_P44_MODE = {
    "FTL": "TRUCKLOAD",
    "LTL": "LTL",
    "PARCEL": "PARCEL",
    "FCL": "OCEAN",
    "LCL": "OCEAN",
    "BULK_OCEAN": "OCEAN",
    "AIR_STD": "AIR",
    "AIR_EXPRESS": "AIR",
    "AIR_CHARTER": "AIR",
    "RAIL_CARLOAD": "RAIL",
    "RAIL_INTERMODAL": "INTERMODAL",
    "RAIL_UNIT": "RAIL",
    "INTERMODAL": "INTERMODAL",
    "DRAYAGE": "DRAYAGE",
    "LAST_MILE": "PARCEL",
}

P44_TO_TMS_MODE = {
    "TRUCKLOAD": "FTL",
    "LTL": "LTL",
    "PARCEL": "PARCEL",
    "OCEAN": "FCL",
    "AIR": "AIR_STD",
    "RAIL": "RAIL_CARLOAD",
    "INTERMODAL": "INTERMODAL",
    "DRAYAGE": "DRAYAGE",
}

# ── EquipmentType ↔ p44 equipment identifier type ─────────────────────────

TMS_TO_P44_EQUIPMENT = {
    "DRY_VAN": "TRAILER",
    "REEFER": "TRAILER",
    "FLATBED": "TRAILER",
    "STEP_DECK": "TRAILER",
    "LOWBOY": "TRAILER",
    "TANKER": "TRAILER",
    "CONTAINER_20": "CONTAINER_ID",
    "CONTAINER_40": "CONTAINER_ID",
    "CONTAINER_40HC": "CONTAINER_ID",
    "CONTAINER_45": "CONTAINER_ID",
    "REEFER_CONTAINER": "CONTAINER_ID",
    "CHASSIS": "CHASSIS",
    "RAILCAR_BOX": "RAIL_CAR_ID",
    "RAILCAR_HOPPER": "RAIL_CAR_ID",
    "RAILCAR_TANK": "RAIL_CAR_ID",
    "SPRINTER_VAN": "TRAILER",
    "BOX_TRUCK": "TRAILER",
}

# ── p44 identifier type strings ────────────────────────────────────────────

P44_IDENTIFIER_TYPES = {
    "BILL_OF_LADING",
    "PURCHASE_ORDER",
    "DELIVERY_NUMBER",
    "SKU",
    "STOCK_KEEPING_UNIT",
    "UNIVERSAL_PRODUCT_CODE",
    "CONTAINER_ID",
    "BOOKING_NUMBER",
    "SHIPMENT_ID",
    "ORDER",
    "TRACKING_NUMBER",
    "PRO_NUMBER",
    "PICKUP_NUMBER",
    "HOUSE_BILL",
    "MASTER_BILL",
}

# ── Carrier identifier type mapping ───────────────────────────────────────

P44_CARRIER_IDENT_TYPES = {
    "SCAC": "SCAC",
    "DOT_NUMBER": "DOT_NUMBER",
    "MC_NUMBER": "MC_NUMBER",
    "P44_EU": "P44_EU",
    "P44_GLOBAL": "P44_GLOBAL",
    "VAT": "VAT",
    "SYSTEM": "SYSTEM",
}


class P44DataMapper:
    """
    Bidirectional mapper between TMS entities and project44 API schemas.

    Stateless utility class — all methods are class or static methods.
    """

    # ════════════════════════════════════════════════════════════════════
    # Shipment → p44 TrackedShipment (outbound)
    # ════════════════════════════════════════════════════════════════════

    @classmethod
    def to_p44_shipment(
        cls,
        shipment: Any,
        carrier: Optional[Any] = None,
        identifiers: Optional[List[Any]] = None,
        stops: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        Convert TMS Shipment to p44 TrackedShipment creation payload.

        Args:
            shipment: Shipment ORM object or dict
            carrier: Carrier ORM object or dict (optional)
            identifiers: List of ShipmentIdentifier ORM objects or dicts
            stops: Pre-built stop list (if not provided, built from origin/destination)

        Returns:
            p44 API payload dict for POST /api/v4/shipments
        """
        ship = cls._to_dict(shipment)

        # Build shipment identifiers
        p44_identifiers = []
        if identifiers:
            for ident in identifiers:
                ident_d = cls._to_dict(ident)
                p44_identifiers.append({
                    "type": ident_d.get("identifier_type", "BILL_OF_LADING"),
                    "value": ident_d.get("identifier_value", ""),
                    "primaryForType": ident_d.get("is_primary", False),
                })
        else:
            # Fallback: use shipment_number as BOL
            p44_identifiers.append({
                "type": "BILL_OF_LADING",
                "value": ship.get("shipment_number", ""),
                "primaryForType": True,
            })

        payload: Dict[str, Any] = {
            "shipmentIdentifiers": p44_identifiers,
        }

        # Carrier identifier
        if carrier:
            carrier_d = cls._to_dict(carrier)
            carrier_ident = cls._build_carrier_identifier(carrier_d)
            if carrier_ident:
                payload["carrierIdentifier"] = carrier_ident

        # Equipment type
        mode = ship.get("mode", "FTL")
        p44_mode = TMS_TO_P44_MODE.get(mode, "TRUCKLOAD")

        equipment = ship.get("required_equipment")
        if equipment:
            p44_equip = TMS_TO_P44_EQUIPMENT.get(equipment, "TRAILER")
            payload["equipmentIdentifierType"] = p44_equip

        # Stops
        if stops:
            payload["stops"] = stops
        else:
            payload["stops"] = cls._build_stops_from_shipment(ship)

        # Attributes
        attributes = {}
        if ship.get("is_hazmat"):
            attributes["isHazmat"] = True
        if ship.get("is_temperature_sensitive"):
            attributes["isTemperatureSensitive"] = True
            if ship.get("temp_min") is not None:
                attributes["temperatureMin"] = ship["temp_min"]
            if ship.get("temp_max") is not None:
                attributes["temperatureMax"] = ship["temp_max"]
        if ship.get("weight"):
            attributes["weight"] = {
                "value": ship["weight"],
                "unit": ship.get("weight_uom", "LBS"),
            }
        if attributes:
            payload["attributes"] = attributes

        return payload

    @classmethod
    def _build_carrier_identifier(cls, carrier: Dict) -> Optional[Dict[str, str]]:
        """Build p44 carrier identifier from Carrier entity."""
        # Prefer p44-specific fields
        if carrier.get("p44_carrier_id") and carrier.get("p44_identifier_type"):
            return {
                "type": carrier["p44_identifier_type"],
                "value": carrier["p44_carrier_id"],
            }
        # Fallback to SCAC
        if carrier.get("scac"):
            return {"type": "SCAC", "value": carrier["scac"]}
        # Fallback to MC number
        if carrier.get("mc_number"):
            return {"type": "MC_NUMBER", "value": carrier["mc_number"]}
        # Fallback to DOT number
        if carrier.get("dot_number"):
            return {"type": "DOT_NUMBER", "value": carrier["dot_number"]}
        return None

    @classmethod
    def _build_stops_from_shipment(cls, ship: Dict) -> List[Dict]:
        """Build p44 stop list from shipment origin/destination."""
        stops = []

        # Origin stop
        origin = ship.get("origin", {})
        if isinstance(origin, dict) and origin:
            stops.append(cls._build_stop(origin, "PICKUP", ship.get("requested_pickup_date")))
        elif ship.get("origin_address"):
            stops.append({
                "type": "PICKUP",
                "address": ship["origin_address"],
            })

        # Destination stop
        dest = ship.get("destination", {})
        if isinstance(dest, dict) and dest:
            stops.append(cls._build_stop(dest, "DELIVERY", ship.get("requested_delivery_date")))
        elif ship.get("destination_address"):
            stops.append({
                "type": "DELIVERY",
                "address": ship["destination_address"],
            })

        return stops

    @classmethod
    def _build_stop(cls, site: Dict, stop_type: str, appt_datetime: Any = None) -> Dict:
        """Build a p44 stop from a Site dict."""
        stop: Dict[str, Any] = {
            "type": stop_type,
            "address": {
                "addressLine1": site.get("address_line_1", ""),
                "city": site.get("city", ""),
                "state": site.get("state_province", ""),
                "postalCode": site.get("postal_code", ""),
                "country": site.get("country", "US"),
            },
        }

        if site.get("name"):
            stop["address"]["name"] = site["name"]
        if site.get("latitude") and site.get("longitude"):
            stop["address"]["coordinates"] = {
                "latitude": site["latitude"],
                "longitude": site["longitude"],
            }

        if appt_datetime:
            dt_str = cls._format_datetime(appt_datetime)
            if dt_str:
                stop["appointmentWindow"] = {
                    "startDateTime": dt_str,
                    "endDateTime": dt_str,
                }

        return stop

    # ════════════════════════════════════════════════════════════════════
    # p44 TrackedShipment → TMS Shipment (inbound)
    # ════════════════════════════════════════════════════════════════════

    @classmethod
    def from_p44_shipment(
        cls,
        p44_data: Dict[str, Any],
        tenant_id: int,
    ) -> Dict[str, Any]:
        """
        Convert p44 TrackedShipment response to TMS Shipment constructor kwargs.

        Returns dict ready for Shipment(**result) or update.
        Does NOT resolve foreign keys (origin_site_id, carrier_id) — caller handles.
        """
        result: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "source": "P44",
            "p44_shipment_id": p44_data.get("id"),
        }

        # Shipment number from first identifier
        identifiers = p44_data.get("shipmentIdentifiers", [])
        if identifiers:
            primary = next(
                (i for i in identifiers if i.get("primaryForType")),
                identifiers[0],
            )
            result["shipment_number"] = primary.get("value", "")

        # Mode
        p44_mode = p44_data.get("mode", "TRUCKLOAD")
        tms_mode = P44_TO_TMS_MODE.get(p44_mode)
        if tms_mode:
            result["mode"] = tms_mode

        # Status mapping
        p44_status = p44_data.get("status", {})
        if isinstance(p44_status, dict):
            result["status"] = cls._map_p44_status(p44_status.get("code", ""))
        elif isinstance(p44_status, str):
            result["status"] = cls._map_p44_status(p44_status)

        # ETA
        eta = p44_data.get("estimatedDeliveryDateTime")
        if eta:
            result["estimated_arrival"] = cls._parse_datetime(eta)

        eta_window = p44_data.get("estimatedDeliveryWindow", {})
        if eta_window:
            result["eta_confidence"] = {
                "p10": eta_window.get("start"),
                "p50": eta,
                "p90": eta_window.get("end"),
                "source": "P44",
            }

        # Tracking URL
        tracking_url = p44_data.get("trackingUrl") or p44_data.get("shareableTrackingUrl")
        if tracking_url:
            result["p44_tracking_url"] = tracking_url

        # Current position
        last_position = p44_data.get("lastPosition", {})
        if last_position:
            coords = last_position.get("coordinates", {})
            if coords.get("latitude"):
                result["current_lat"] = coords["latitude"]
            if coords.get("longitude"):
                result["current_lon"] = coords["longitude"]
            result["last_tracking_update"] = cls._parse_datetime(
                last_position.get("dateTime")
            ) or datetime.utcnow()

        # Weight from attributes
        attrs = p44_data.get("attributes", {})
        weight_data = attrs.get("weight", {})
        if weight_data.get("value"):
            result["weight"] = weight_data["value"]
            result["weight_uom"] = weight_data.get("unit", "LBS")

        return result

    @classmethod
    def _map_p44_status(cls, p44_code: str) -> str:
        """Map p44 shipment status code to TMS ShipmentStatus value."""
        mapping = {
            "TRACKING": "IN_TRANSIT",
            "IN_TRANSIT": "IN_TRANSIT",
            "DELIVERED": "DELIVERED",
            "COMPLETED": "DELIVERED",
            "CANCELLED": "CANCELLED",
            "PENDING": "TENDERED",
            "CREATED": "DRAFT",
            "AT_STOP": "AT_STOP",
            "OUT_FOR_DELIVERY": "OUT_FOR_DELIVERY",
            "PICKED_UP": "IN_TRANSIT",
        }
        return mapping.get(p44_code.upper(), "DRAFT") if p44_code else "DRAFT"

    # ════════════════════════════════════════════════════════════════════
    # ShipmentIdentifier ↔ p44 shipmentIdentifiers
    # ════════════════════════════════════════════════════════════════════

    @classmethod
    def to_p44_identifiers(cls, identifiers: List[Any]) -> List[Dict[str, Any]]:
        """Convert TMS ShipmentIdentifier list to p44 format."""
        result = []
        for ident in identifiers:
            d = cls._to_dict(ident)
            result.append({
                "type": d.get("identifier_type", "BILL_OF_LADING"),
                "value": d.get("identifier_value", ""),
                "primaryForType": d.get("is_primary", False),
            })
        return result

    @classmethod
    def from_p44_identifiers(
        cls,
        p44_identifiers: List[Dict],
        shipment_id: int,
        tenant_id: int,
    ) -> List[Dict[str, Any]]:
        """
        Convert p44 shipmentIdentifiers array to TMS ShipmentIdentifier dicts.

        Returns list of dicts ready for ShipmentIdentifier(**result).
        """
        results = []
        for ident in p44_identifiers:
            ident_type = ident.get("type", "")
            ident_value = ident.get("value", "")
            if not ident_value:
                continue
            results.append({
                "shipment_id": shipment_id,
                "identifier_type": ident_type,
                "identifier_value": ident_value,
                "is_primary": ident.get("primaryForType", False),
                "source": "P44",
                "tenant_id": tenant_id,
            })
        return results

    # ════════════════════════════════════════════════════════════════════
    # TrackingEvent ↔ p44 TrackedShipmentEvent
    # ════════════════════════════════════════════════════════════════════

    @classmethod
    def from_p44_tracking_event(
        cls,
        p44_event: Dict[str, Any],
        shipment_id: int,
        tenant_id: int,
        p44_shipment_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Convert a p44 event object to TMS TrackingEvent constructor kwargs.

        This is the same logic as webhook_handler._process_tracking_event
        but returns a dict instead of creating ORM objects.
        """
        from .webhook_handler import P44_EVENT_TYPE_MAP

        p44_type = p44_event.get("type", "UPDATED")
        tms_type = P44_EVENT_TYPE_MAP.get(p44_type, "UPDATED")

        location = p44_event.get("location", {})
        address = location.get("address", {})
        coordinates = location.get("coordinates", {})
        vessel = p44_event.get("vessel", {})
        container = p44_event.get("container", {})
        equipment = p44_event.get("equipmentIdentifier", {})
        temp_data = p44_event.get("temperature", {})

        return {
            "shipment_id": shipment_id,
            "event_type": tms_type,
            "event_timestamp": cls._parse_datetime(p44_event.get("dateTime")) or datetime.utcnow(),
            "received_timestamp": datetime.utcnow(),
            "p44_event_id": p44_event.get("eventId"),
            "p44_shipment_id": p44_shipment_id,
            "p44_shipment_leg_id": p44_event.get("shipmentLegId"),
            # Location
            "location_name": location.get("name"),
            "address_line_1": address.get("addressLine1"),
            "city": address.get("city"),
            "state": address.get("state"),
            "postal_code": address.get("postalCode"),
            "country": address.get("country"),
            "latitude": coordinates.get("latitude"),
            "longitude": coordinates.get("longitude"),
            # Status
            "status_code": p44_event.get("statusCode"),
            "status_description": p44_event.get("description"),
            # ETA
            "estimated_arrival": cls._parse_datetime(p44_event.get("estimateDateTime")),
            "estimated_departure": cls._parse_datetime(p44_event.get("estimateDepartureDateTime")),
            # Stop
            "stop_sequence": p44_event.get("stopSequence"),
            "stop_type": p44_event.get("stopType"),
            # Ocean
            "vessel_name": vessel.get("name"),
            "voyage_number": vessel.get("voyageNumber"),
            "vessel_imo": vessel.get("imo"),
            "port_locode": p44_event.get("portLocode"),
            "container_number": container.get("number") or p44_event.get("containerNumber"),
            "seal_number": container.get("sealNumber"),
            # Equipment
            "equipment_identifier_type": equipment.get("type"),
            "equipment_identifier_value": equipment.get("value"),
            # Temperature
            "temperature": temp_data.get("value"),
            "temperature_uom": temp_data.get("unit", "F"),
            "temperature_set_point": temp_data.get("setPoint"),
            # Exception
            "exception_code": p44_event.get("exceptionCode"),
            "exception_description": p44_event.get("exceptionDescription"),
            # Source
            "source": "P44",
            "raw_payload": p44_event,
            "tenant_id": tenant_id,
        }

    @classmethod
    def to_p44_tracking_events_query(
        cls,
        shipment_id: str,
    ) -> str:
        """Return the p44 API path for tracking events."""
        return f"/api/v4/shipments/{shipment_id}/tracking"

    # ════════════════════════════════════════════════════════════════════
    # Carrier ↔ p44 CapacityProvider
    # ════════════════════════════════════════════════════════════════════

    @classmethod
    def to_p44_carrier_identifier(cls, carrier: Any) -> Optional[Dict[str, str]]:
        """Convert TMS Carrier to p44 CapacityProviderIdentifier."""
        d = cls._to_dict(carrier)
        return cls._build_carrier_identifier(d)

    @classmethod
    def from_p44_carrier(
        cls,
        p44_carrier: Dict[str, Any],
        tenant_id: int,
    ) -> Dict[str, Any]:
        """
        Convert p44 carrier/capacity provider info to TMS Carrier kwargs.

        p44 carrier data comes from:
        - /api/v4/capacityproviders/accounts
        - TrackedShipment.carrierIdentifier
        """
        ident = p44_carrier.get("identifier", {})
        if not ident and p44_carrier.get("type"):
            ident = {"type": p44_carrier.get("type"), "value": p44_carrier.get("value")}

        result: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "source": "P44",
        }

        # Name
        result["name"] = (
            p44_carrier.get("name")
            or p44_carrier.get("displayName")
            or ident.get("value", "Unknown Carrier")
        )

        # SCAC (most common identifier type)
        ident_type = ident.get("type", "")
        ident_value = ident.get("value", "")

        if ident_type == "SCAC":
            result["code"] = ident_value
            result["scac"] = ident_value
        elif ident_type == "DOT_NUMBER":
            result["code"] = f"DOT-{ident_value}"
            result["dot_number"] = ident_value
        elif ident_type == "MC_NUMBER":
            result["code"] = f"MC-{ident_value}"
            result["mc_number"] = ident_value
        else:
            result["code"] = ident_value or "UNKNOWN"

        # p44 integration fields
        result["p44_carrier_id"] = ident_value
        result["p44_identifier_type"] = ident_type

        # Account info
        account_group = p44_carrier.get("accountGroupInfo", {})
        if account_group.get("code"):
            result["p44_account_group_code"] = account_group["code"]

        account_info = p44_carrier.get("accountInfo", {})
        if account_info.get("code"):
            result["p44_account_code"] = account_info["code"]

        # Modes
        modes = p44_carrier.get("supportedModes", [])
        if modes:
            result["modes"] = [P44_TO_TMS_MODE.get(m, m) for m in modes]

        # Default carrier type based on mode
        result["carrier_type"] = cls._infer_carrier_type(modes, ident_type)

        return result

    @classmethod
    def _infer_carrier_type(cls, modes: List[str], ident_type: str) -> str:
        """Infer TMS CarrierType from p44 mode and identifier type."""
        if "OCEAN" in modes:
            return "OCEAN_LINE"
        if "AIR" in modes:
            return "AIRLINE"
        if "RAIL" in modes:
            return "RAILROAD"
        if ident_type in ("P44_EU", "P44_GLOBAL"):
            return "ASSET"
        return "ASSET"

    # ════════════════════════════════════════════════════════════════════
    # Ocean Shipment Mapping
    # ════════════════════════════════════════════════════════════════════

    @classmethod
    def to_p44_ocean_shipment(
        cls,
        container_number: Optional[str] = None,
        bill_of_lading: Optional[str] = None,
        booking_number: Optional[str] = None,
        carrier_scac: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build p44 ocean tracking creation payload."""
        identifiers = []
        if container_number:
            identifiers.append({"type": "CONTAINER_ID", "value": container_number})
        if bill_of_lading:
            identifiers.append({"type": "BILL_OF_LADING", "value": bill_of_lading})
        if booking_number:
            identifiers.append({"type": "BOOKING_NUMBER", "value": booking_number})

        payload: Dict[str, Any] = {"shipmentIdentifiers": identifiers}
        if carrier_scac:
            payload["carrierIdentifier"] = {"type": "SCAC", "value": carrier_scac}

        return payload

    @classmethod
    def from_p44_ocean_tracking(
        cls,
        p44_data: Dict[str, Any],
        shipment_id: int,
        tenant_id: int,
    ) -> Dict[str, Any]:
        """
        Extract ocean tracking details from p44 ocean response.

        Returns dict with fields to update on Shipment + list of tracking events.
        """
        result: Dict[str, Any] = {
            "shipment_updates": {},
            "tracking_events": [],
        }

        # Container info
        containers = p44_data.get("containers", [])
        if containers:
            container = containers[0]
            result["shipment_updates"]["container_number"] = container.get("containerNumber")

        # Vessel info
        vessel = p44_data.get("vessel", {})
        if vessel:
            result["vessel_name"] = vessel.get("name")
            result["vessel_imo"] = vessel.get("imo")
            result["voyage_number"] = vessel.get("voyageNumber")

        # Events
        events = p44_data.get("events", [])
        for event in events:
            te = cls.from_p44_tracking_event(
                event, shipment_id, tenant_id,
                p44_shipment_id=p44_data.get("id"),
            )
            result["tracking_events"].append(te)

        # ETA
        eta = p44_data.get("estimatedArrivalDateTime")
        if eta:
            result["shipment_updates"]["estimated_arrival"] = cls._parse_datetime(eta)

        return result

    # ════════════════════════════════════════════════════════════════════
    # Port Intelligence Mapping
    # ════════════════════════════════════════════════════════════════════

    @classmethod
    def from_p44_port_intelligence(
        cls,
        p44_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Normalize p44 port intelligence response.

        Returns dict with congestion metrics per port.
        """
        ports = {}
        for port in p44_data.get("results", []):
            locode = port.get("locode", "")
            ports[locode] = {
                "locode": locode,
                "name": port.get("name"),
                "country": port.get("country"),
                "congestion_level": port.get("congestionLevel"),
                "avg_dwell_days": port.get("averageDwellTimeDays"),
                "avg_wait_days": port.get("averageWaitTimeDays"),
                "vessel_count": port.get("vesselCount"),
                "import_dwell_days": port.get("importDwellTimeDays"),
                "export_dwell_days": port.get("exportDwellTimeDays"),
                "updated_at": cls._parse_datetime(port.get("lastUpdated")),
            }
        return ports

    # ════════════════════════════════════════════════════════════════════
    # Bulk / Search Result Mapping
    # ════════════════════════════════════════════════════════════════════

    @classmethod
    def from_p44_search_results(
        cls,
        p44_data: Dict[str, Any],
        tenant_id: int,
    ) -> Dict[str, Any]:
        """
        Convert p44 shipment search results to TMS format.

        Returns:
            {
                "shipments": [list of Shipment dicts],
                "next_page_token": str or None,
                "total_count": int
            }
        """
        results = p44_data.get("results", [])
        shipments = [
            cls.from_p44_shipment(r, tenant_id)
            for r in results
        ]

        return {
            "shipments": shipments,
            "next_page_token": p44_data.get("nextPageToken"),
            "total_count": p44_data.get("totalCount", len(results)),
        }

    # ════════════════════════════════════════════════════════════════════
    # Helpers
    # ════════════════════════════════════════════════════════════════════

    @staticmethod
    def _to_dict(obj: Any) -> Dict[str, Any]:
        """Convert ORM object or dict to plain dict."""
        if isinstance(obj, dict):
            return obj
        # SQLAlchemy ORM object
        if hasattr(obj, "__dict__"):
            d = {}
            for key, value in obj.__dict__.items():
                if not key.startswith("_"):
                    if hasattr(value, 'value'):
                        d[key] = value.value
                    else:
                        d[key] = value
            return d
        return {}

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        """Parse ISO 8601 datetime from p44."""
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            cleaned = str(value).replace("Z", "+00:00")
            dt = datetime.fromisoformat(cleaned)
            return dt.replace(tzinfo=None)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _format_datetime(value: Any) -> Optional[str]:
        """Format datetime for p44 API (ISO 8601 with Z)."""
        if not value:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%dT%H:%M:%SZ")
        return None
