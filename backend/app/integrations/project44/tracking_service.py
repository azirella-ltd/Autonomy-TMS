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

    # ── Document API (Gap #4) ───────────────────────────────────────────

    async def get_documents(
        self,
        shipment_id: str,
        document_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get documents attached to a p44 shipment.

        Returns a list of document metadata dicts. Each dict contains:
          documentType, url, fileName, createdDate, etc.

        Common document types: BOL, POD, INVOICE, CUSTOMS, PACKING_LIST.
        """
        params = {}
        if document_types:
            params["documentTypes"] = ",".join(document_types)
        resp = await self.connector.get(
            f"{self.SHIPMENTS_BASE}/{shipment_id}/documents", params=params
        )
        return resp.get("results", resp.get("documents", []))

    # ── Port Intelligence Sync (Gap #5) ────────────────────────────────

    async def sync_port_intelligence_to_lane_profiles(
        self,
        db_session,
        tenant_id: int,
        locodes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Sync p44 port intelligence into LaneProfile risk scores.

        Fetches congestion/dwell data from p44 for ocean-leg ports and
        updates the corresponding LaneProfile entries' disruption_frequency
        and congestion_risk_score fields. The DemandSensingTRM and
        CapacityBufferTRM already read these fields — this gives them
        real-time signal quality from p44.

        Args:
            db_session: async SQLAlchemy session
            tenant_id: scope to this tenant's lane profiles
            locodes: optional explicit port list; if None, auto-discovers
                     from LaneProfile origin/destination regions that look
                     like UN/LOCODE patterns

        Returns:
            {"ports_queried": N, "profiles_updated": N}
        """
        from sqlalchemy import select
        from ...models.transportation_config import LaneProfile
        from .data_mapper import P44DataMapper

        # Find ocean-mode lanes for this tenant
        stmt = select(LaneProfile).where(
            LaneProfile.tenant_id == tenant_id,
            LaneProfile.primary_mode.in_(["OCEAN", "FCL", "LCL", "BULK_OCEAN"]),
            LaneProfile.is_active == True,
        )
        result = await db_session.execute(stmt)
        ocean_lanes = result.scalars().all()

        if not ocean_lanes:
            return {"ports_queried": 0, "profiles_updated": 0}

        # Collect port LOCODEs from lane regions (origin/destination)
        if locodes is None:
            locodes_set = set()
            for lane in ocean_lanes:
                # Regions that look like UN/LOCODEs (5-char codes like USLAX, CNSHA)
                for region in [lane.origin_region, lane.destination_region]:
                    if region and len(region) == 5 and region.isalpha():
                        locodes_set.add(region.upper())
            locodes = list(locodes_set)

        if not locodes:
            return {"ports_queried": 0, "profiles_updated": 0}

        # Fetch from p44 (max 10 per call)
        all_ports = {}
        for i in range(0, len(locodes), 10):
            batch = locodes[i:i + 10]
            try:
                raw = await self.get_port_intelligence(batch)
                mapped = P44DataMapper.from_p44_port_intelligence(raw)
                all_ports.update(mapped)
            except Exception as e:
                logger.warning(f"P44 port intelligence batch failed for {batch}: {e}")

        if not all_ports:
            return {"ports_queried": len(locodes), "profiles_updated": 0}

        # Update LaneProfile risk scores based on port data
        updated = 0
        for lane in ocean_lanes:
            origin_data = all_ports.get(lane.origin_region, {}) if lane.origin_region else {}
            dest_data = all_ports.get(lane.destination_region, {}) if lane.destination_region else {}

            # Use the worse of origin/destination congestion
            congestion_levels = {
                "LOW": 0.2, "MODERATE": 0.4, "HIGH": 0.6,
                "VERY_HIGH": 0.8, "CRITICAL": 1.0,
            }

            scores = []
            for port_data in [origin_data, dest_data]:
                if port_data.get("congestion_level"):
                    scores.append(congestion_levels.get(
                        port_data["congestion_level"].upper(), 0.5
                    ))

            if scores:
                lane.congestion_risk_score = max(scores)
                # Dwell time > 5 days suggests frequent disruption
                avg_dwell = max(
                    origin_data.get("avg_dwell_days") or 0,
                    dest_data.get("avg_dwell_days") or 0,
                )
                if avg_dwell > 0:
                    lane.disruption_frequency = min(avg_dwell / 10.0, 1.0)
                updated += 1

        if updated:
            await db_session.flush()

        logger.info(
            f"P44 port intelligence sync: queried {len(locodes)} ports, "
            f"updated {updated} lane profiles for tenant {tenant_id}"
        )
        return {"ports_queried": len(locodes), "profiles_updated": updated}

    # ── Document Sync for Shipment (Gap #4) ────────────────────────────

    async def sync_documents_for_shipment(
        self,
        p44_shipment_id: str,
        tms_shipment_id: int,
        tenant_id: int,
        db_session,
    ) -> Dict[str, Any]:
        """
        Sync p44 documents (BOL, POD) into TMS BillOfLading/ProofOfDelivery.

        Call this after a shipment is delivered (DELIVERED status event).
        p44 often has the signed delivery receipt before the TMS does
        (because p44 gets it from the driver app), shortening the POD cycle.

        Returns: {"bol_synced": bool, "pod_synced": bool, "documents_found": N}
        """
        from sqlalchemy import select
        from ...models.tms_entities import BillOfLading, ProofOfDelivery

        try:
            docs = await self.get_documents(p44_shipment_id, ["BOL", "POD"])
        except Exception as e:
            logger.warning(f"P44 document fetch failed for {p44_shipment_id}: {e}")
            return {"bol_synced": False, "pod_synced": False, "documents_found": 0}

        result = {"bol_synced": False, "pod_synced": False, "documents_found": len(docs)}

        for doc in docs:
            doc_type = (doc.get("documentType") or doc.get("type", "")).upper()
            doc_url = doc.get("url") or doc.get("downloadUrl")

            if doc_type == "BOL" and doc_url:
                # Check if we already have a BOL with a p44 URL
                existing = await db_session.execute(
                    select(BillOfLading).where(
                        BillOfLading.shipment_id == tms_shipment_id,
                        BillOfLading.tenant_id == tenant_id,
                    )
                )
                bol = existing.scalar_one_or_none()
                if bol and not bol.document_url:
                    # TMS has a BOL record but no document — fill from p44
                    bol.document_url = doc_url
                    result["bol_synced"] = True
                elif not bol:
                    # Create a BOL record from p44 document
                    bol = BillOfLading(
                        shipment_id=tms_shipment_id,
                        bol_number=doc.get("referenceNumber", f"P44-{p44_shipment_id}"),
                        document_url=doc_url,
                        issued_date=datetime.utcnow().date(),
                        tenant_id=tenant_id,
                    )
                    db_session.add(bol)
                    result["bol_synced"] = True

            elif doc_type == "POD" and doc_url:
                existing = await db_session.execute(
                    select(ProofOfDelivery).where(
                        ProofOfDelivery.shipment_id == tms_shipment_id,
                        ProofOfDelivery.tenant_id == tenant_id,
                    )
                )
                pod = existing.scalar_one_or_none()
                if pod and not pod.document_url:
                    pod.document_url = doc_url
                    if not pod.signature_url:
                        pod.signature_url = doc_url  # POD document often IS the signed receipt
                    result["pod_synced"] = True
                elif not pod:
                    pod = ProofOfDelivery(
                        shipment_id=tms_shipment_id,
                        delivery_date=datetime.utcnow(),
                        delivery_status="FULL",
                        document_url=doc_url,
                        tenant_id=tenant_id,
                    )
                    db_session.add(pod)
                    result["pod_synced"] = True

        if result["bol_synced"] or result["pod_synced"]:
            await db_session.flush()

        logger.info(
            f"P44 document sync for shipment {tms_shipment_id}: "
            f"{result['documents_found']} docs, BOL={'synced' if result['bol_synced'] else 'no'}, "
            f"POD={'synced' if result['pod_synced'] else 'no'}"
        )
        return result
