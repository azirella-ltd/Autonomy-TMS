"""
project44 Shipment Tracking Service

Provides high-level operations for shipment lifecycle management
against the project44 API v4:
- Create tracked shipments (truckload, LTL, ocean, intermodal)
- Get tracking status and events
- Update shipment details
- Cancel/delete shipments
- Get ETA predictions
- Bulk tracking operations

All methods return parsed p44 response dicts. Use P44DataMapper
to convert to/from TMS entities.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from .connector import P44Connector

logger = logging.getLogger(__name__)


class P44TrackingService:
    """
    Shipment tracking operations against project44 API v4.

    Endpoints:
    - POST   /api/v4/shipments                  — Create shipment
    - GET    /api/v4/shipments/{id}              — Get shipment details
    - PUT    /api/v4/shipments/{id}              — Update shipment
    - POST   /api/v4/shipments/{id}/cancel       — Cancel shipment
    - DELETE /api/v4/shipments/{id}              — Delete shipment
    - GET    /api/v4/shipments/{id}/tracking     — Get tracking history
    - POST   /api/v4/shipments/search            — Search shipments
    """

    # ── API Paths ────────────────────────────────────────────────────────
    SHIPMENTS_BASE = "/api/v4/shipments"
    OCEAN_TRACKING_BASE = "/api/v4/ocean/tracking"
    PORT_INTEL_BASE = "/api/v4/portintel"

    def __init__(self, connector: P44Connector):
        self.connector = connector

    # ── Truckload / LTL Shipment Operations ──────────────────────────────

    async def create_shipment(
        self,
        identifiers: List[Dict[str, str]],
        carrier_identifier: Dict[str, str],
        mode: str = "TRUCKLOAD",
        equipment_type: Optional[str] = None,
        stops: Optional[List[Dict]] = None,
        attributes: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Create a tracked shipment in project44.

        Args:
            identifiers: List of {"type": "BILL_OF_LADING", "value": "BOL123", "primaryForType": True}
            carrier_identifier: {"type": "SCAC", "value": "ABCD"}
            mode: TRUCKLOAD, LTL, PARCEL, INTERMODAL
            equipment_type: TRAILER, CONTAINER, etc.
            stops: List of stop objects with address and appointment windows
            attributes: Additional shipment attributes

        Returns:
            p44 TrackedShipment response with shipmentId (UUID)
        """
        payload: Dict[str, Any] = {
            "shipmentIdentifiers": identifiers,
            "carrierIdentifier": carrier_identifier,
        }

        if equipment_type:
            payload["equipmentIdentifierType"] = equipment_type
        if stops:
            payload["stops"] = stops
        if attributes:
            payload["attributes"] = attributes

        logger.info(f"P44: Creating {mode} shipment, carrier={carrier_identifier.get('value')}")
        result = await self.connector.post(self.SHIPMENTS_BASE, payload)
        logger.info(f"P44: Created shipment {result.get('id', 'unknown')}")
        return result

    async def get_shipment(self, shipment_id: str) -> Dict[str, Any]:
        """Get shipment details by p44 shipment ID (UUID)."""
        return await self.connector.get(f"{self.SHIPMENTS_BASE}/{shipment_id}")

    async def get_tracking_history(self, shipment_id: str) -> Dict[str, Any]:
        """
        Get full tracking event history for a shipment.

        Returns events in ascending order by event timestamp.
        Includes: position updates, status changes, ETA updates, exceptions.
        """
        return await self.connector.get(f"{self.SHIPMENTS_BASE}/{shipment_id}/tracking")

    async def update_shipment(
        self,
        shipment_id: str,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update shipment details (identifiers, stops, attributes)."""
        return await self.connector.put(
            f"{self.SHIPMENTS_BASE}/{shipment_id}",
            updates,
        )

    async def cancel_shipment(self, shipment_id: str) -> Dict[str, Any]:
        """Cancel a tracked shipment."""
        logger.info(f"P44: Cancelling shipment {shipment_id}")
        return await self.connector.post(
            f"{self.SHIPMENTS_BASE}/{shipment_id}/cancel",
            {},
        )

    async def delete_shipment(self, shipment_id: str) -> Dict[str, Any]:
        """Delete a tracked shipment (removes from p44)."""
        logger.info(f"P44: Deleting shipment {shipment_id}")
        return await self.connector.delete(f"{self.SHIPMENTS_BASE}/{shipment_id}")

    async def search_shipments(
        self,
        identifier_type: Optional[str] = None,
        identifier_value: Optional[str] = None,
        carrier_scac: Optional[str] = None,
        status: Optional[str] = None,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        page_size: int = 50,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search shipments with filters.

        Returns paginated results with nextPageToken for cursor-based pagination.
        """
        payload: Dict[str, Any] = {
            "pageSize": page_size,
        }
        if identifier_type and identifier_value:
            payload["shipmentIdentifiers"] = [
                {"type": identifier_type, "value": identifier_value}
            ]
        if carrier_scac:
            payload["carrierIdentifier"] = {"type": "SCAC", "value": carrier_scac}
        if status:
            payload["statuses"] = [status]
        if created_after:
            payload["createdDateTimeRange"] = payload.get("createdDateTimeRange", {})
            payload["createdDateTimeRange"]["startDateTime"] = created_after.isoformat() + "Z"
        if created_before:
            payload["createdDateTimeRange"] = payload.get("createdDateTimeRange", {})
            payload["createdDateTimeRange"]["endDateTime"] = created_before.isoformat() + "Z"
        if page_token:
            payload["pageToken"] = page_token

        return await self.connector.post(f"{self.SHIPMENTS_BASE}/search", payload)

    # ── Equipment / Asset Tracking ───────────────────────────────────────

    async def assign_equipment(
        self,
        shipment_id: str,
        equipment_type: str,
        equipment_value: str,
        shipment_leg_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Assign equipment identifier to a shipment.

        Args:
            equipment_type: CONTAINER_ID, RAIL_CAR_ID, TRAILER_ID
            equipment_value: The identifier value (e.g., trailer number)
        """
        payload = {
            "equipmentIdentifier": {
                "type": equipment_type,
                "value": equipment_value,
            }
        }
        if shipment_leg_id:
            payload["shipmentLegId"] = shipment_leg_id

        return await self.connector.post(
            f"{self.SHIPMENTS_BASE}/{shipment_id}/equipment",
            payload,
        )

    # ── Ocean Tracking ───────────────────────────────────────────────────

    async def create_ocean_shipment(
        self,
        container_number: Optional[str] = None,
        bill_of_lading: Optional[str] = None,
        booking_number: Optional[str] = None,
        carrier_scac: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create an ocean shipment for tracking.

        At least one identifier required: container number, BOL, or booking number.
        Carrier SCAC recommended for faster matching.
        """
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

        return await self.connector.post(self.OCEAN_TRACKING_BASE, payload)

    async def get_ocean_tracking(self, shipment_id: str) -> Dict[str, Any]:
        """Get ocean tracking details including vessel, port calls, ETAs."""
        return await self.connector.get(f"{self.OCEAN_TRACKING_BASE}/{shipment_id}")

    # ── Port Intelligence ────────────────────────────────────────────────

    async def get_port_intelligence(
        self,
        locodes: List[str],
        format: str = "json",
    ) -> Dict[str, Any]:
        """
        Get port intelligence for 1-10 UN/LOCODE port codes.

        Includes: congestion levels, avg dwell times, vessel wait times.
        """
        params = {"locodes": ",".join(locodes[:10])}
        return await self.connector.get(self.PORT_INTEL_BASE, params=params)

    # ── Bulk Operations ──────────────────────────────────────────────────

    async def bulk_create_shipments(
        self,
        shipments: List[Dict[str, Any]],
        batch_size: int = 25,
    ) -> List[Dict[str, Any]]:
        """
        Create multiple shipments with batching.

        p44 doesn't have a native bulk endpoint, so we batch concurrent requests.
        """
        import asyncio
        results = []
        for i in range(0, len(shipments), batch_size):
            batch = shipments[i:i + batch_size]
            tasks = [
                self.connector.post(self.SHIPMENTS_BASE, shipment)
                for shipment in batch
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.error(f"P44 bulk create error for shipment {i+j}: {result}")
                    results.append({"error": str(result), "index": i + j})
                else:
                    results.append(result)
        return results

    # ── Carrier Connectivity ─────────────────────────────────────────────

    async def get_carrier_accounts(self) -> Dict[str, Any]:
        """Get all carrier accounts connected to this p44 instance."""
        return await self.connector.get("/api/v4/capacityproviders/accounts")

    async def get_carrier_account_groups(self) -> Dict[str, Any]:
        """Get carrier account groups."""
        return await self.connector.get("/api/v4/capacityproviders/accountgroups")
