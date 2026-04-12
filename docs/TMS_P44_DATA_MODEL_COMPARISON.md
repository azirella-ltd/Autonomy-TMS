# TMS Data Model vs project44 Data Model — Comparison & Advice

**Created:** 2026-04-12
**Sister doc:** [TMS_DATA_MODEL.md](TMS_DATA_MODEL.md)

## What p44 is and isn't

p44 is a visibility platform, not a TMS. Their data model covers the tracking and observation of shipments: where they are, what happened, when they'll arrive. It does not cover the planning and execution of transportation: load building, carrier procurement, rate management, dock scheduling, capacity planning, or operational decision-making.

That distinction is the key to understanding the comparison:

| Domain | p44 provides | TMS provides |
|---|---|---|
| Tracking & visibility | Core competency — deep, multi-modal, real-time | Consumes from p44 via TrackingEvent |
| Shipment lifecycle | Create/track/cancel via API | Full lifecycle from DRAFT → CLOSED |
| ETA prediction | Conformal ETA ranges (P10/P50/P90) | Stores p44's ETA + own conformal layer |
| Carrier identity | SCAC/MC/DOT/P44_EU/P44_GLOBAL | Same + contract/scorecard/tender |
| Equipment | Identifier types (TRAILER/CONTAINER_ID/RAIL_CAR_ID) | Full equipment fleet model with specs |
| Load planning | Not modeled | Full Load/LoadItem model |
| Rate management | Not modeled | FreightRate + CarrierContract |
| Dock scheduling | Not modeled | DockDoor + Appointment model |
| Exception management | Detects exceptions (DELAYED, EXCEPTION events) | Full resolution lifecycle (ShipmentException + ExceptionResolution + AIIO) |
| Capacity planning | Not modeled | ShippingForecast + CapacityTarget + TransportationPlan |
| Commodity/freight class | Not modeled (treats freight as opaque cargo) | CommodityHierarchy + Commodity |
| Documents | Multi-modal document API (BOL, POD, invoice) | BillOfLading + ProofOfDelivery |

---

## Entity-by-entity alignment

### Well-aligned (the integration is working correctly)

| TMS Entity | p44 Entity | Alignment quality | Notes |
|---|---|---|---|
| TrackingEvent | TrackedShipmentEvent | Excellent | 1:1 field mapping via `from_p44_tracking_event()`. All 25+ p44 event types mapped. `p44_event_id` enables deduplication. Raw payload stored for audit. Ocean-specific fields (vessel, container, port) all covered. |
| ShipmentIdentifier | shipmentIdentifiers[] | Excellent | Same identifier type enum (BILL_OF_LADING, PRO_NUMBER, CONTAINER_ID, BOOKING_NUMBER, etc.). Bidirectional mapping in place. `primaryForType` flag preserved. |
| Carrier (identity fields) | CapacityProviderIdentifier | Excellent | SCAC/MC_NUMBER/DOT_NUMBER/P44_EU/P44_GLOBAL/VAT all mapped. `p44_carrier_id` + `p44_identifier_type` stored on carrier entity for stable lookup. |
| ShipmentLeg | p44 shipmentLegs | Good | Leg-level tracking with `p44_shipment_leg_id`. Covers multi-modal journeys (ocean→drayage→rail). |
| Shipment (tracking fields) | TrackedShipment | Good | ETA, position, status, tracking URL all flow inbound. `eta_confidence` JSON stores p44's P10/P50/P90 range. |

---

## Gaps worth addressing

### 1. p44 Shipment Status model is richer than TMS consumes

p44's status model is a nested object (`{ code, description, derivedStatus, health }`) with both a raw status code and a "derived" health assessment. TMS currently flattens this to a single status string via `_map_p44_status()` (line 376-390 of `data_mapper.py`). The `derivedStatus` and `health` score are lost.

**Recommendation:** Add `p44_derived_status` and `p44_health_score` columns to `tms_shipment` (or store in the existing `eta_confidence` JSON). The health score is valuable input to the ExceptionManagementTRM — a degrading health score is a leading indicator of an upcoming exception before p44 formally fires an EXCEPTION event.

### 2. p44 Order/Load model vs TMS Load model

p44 recently (v4) introduced Order and Load as first-class entities sitting above individual tracked shipments. An Order can contain multiple Loads; a Load can contain multiple shipment legs. TMS has its own Load and LoadItem entities, but these aren't mapped to p44's — they're TMS-internal planning constructs.

**Recommendation:** Map `tms_shipment.load_id` ↔ p44 `masterShipmentId` (the p44 concept closest to a Load). When p44 publishes `inventory.v1.load.upserted` webhook events, create or update the corresponding TMS Load. This closes the loop between TMS load planning and p44 load-level visibility. Not urgent — individual shipment tracking works fine without it — but it becomes important for multi-stop loads where p44 tracks stops at the load level, not the individual shipment level.

### 3. p44 ETA confidence model

p44 publishes `estimatedDeliveryWindow` with `startDateTime` and `endDateTime`. TMS stores this as `eta_confidence: { p10, p50, p90, source }` JSON. But TMS's own conformal prediction layer also produces P10/P50/P90 bounds. The two ranges should be compared, not merged. Right now they're likely overwriting each other depending on which updates last.

**Recommendation:** Store p44's range and Autonomy's conformal range separately:

```json
{
    "p44": { "p10": "...", "p50": "...", "p90": "..." },
    "autonomy": { "p10": "...", "p50": "...", "p90": "..." },
    "composite": { "p10": "...", "p50": "...", "p90": "...", "method": "ensemble" }
}
```

The composite is what the ShipmentTrackingTRM should use; the split gives auditability on where the confidence came from and enables a "which model is better" analysis over time.

### 4. p44 Document API

p44 has a Multi-Modal Document API for fetching BOLs, PODs, invoices, and customs documents attached to shipments. TMS has BillOfLading and ProofOfDelivery models but these are TMS-authored — they don't pull from p44.

**Recommendation:** Add an inbound sync for p44 documents. When a shipment is delivered, call p44's `GET /documents?shipmentId=...` endpoint and populate the TMS BOL/POD records with `source: "P44"`. For POD specifically, p44 often has the signed delivery receipt before the TMS does (because p44 gets it from the driver app). This shortens the POD cycle.

### 5. p44 Port Intelligence ↔ TMS LaneProfile

The data mapper has `from_p44_port_intelligence()` (line 693) which normalizes p44 port congestion metrics. But these aren't currently written to any TMS entity — the data mapper returns a dict that presumably gets used ephemerally.

**Recommendation:** Wire port intelligence data into LaneProfile fields (`disruption_frequency`, `congestion_risk_score`) for lanes that have ocean legs. Run a periodic sync (daily?) that updates lane risk scores based on current port conditions. The DemandSensingTRM and CapacityBufferTRM already read these fields — they'd get free signal quality improvement.

### 6. p44 Appointment Update events

p44 publishes `APPOINTMENT_SET` and `UPDATED_DELIVERY_APPT` events. TMS maps these to tracking events but doesn't update the TMS Appointment entity. The TMS dock scheduling system and p44's appointment awareness are disconnected.

**Recommendation:** When a `UPDATED_DELIVERY_APPT` event arrives via webhook, look up the corresponding Appointment by `(shipment_id, site_id)` and update `scheduled_start`/`scheduled_end`. This keeps the DockSchedulingTRM's view of appointments in sync with what the carrier is actually confirming through p44.

---

## TMS entities that have no p44 equivalent (and shouldn't)

These are the planning and execution entities that are core TMS business logic and have no p44 counterpart. This is by design — TMS is the system of record for decisions, p44 is the system of record for visibility.

| TMS Entity | Why it has no p44 equivalent |
|---|---|
| CommodityHierarchy / Commodity | What's being shipped — p44 treats cargo as opaque |
| FacilityConfig / OperatingSchedule / YardLocation | Facility operations — not a visibility concern |
| CarrierLane / LaneProfile | Strategic lane management — TMS planning domain |
| CarrierContract / CarrierScorecard | Procurement and performance — TMS domain |
| FreightRate | Rate management — TMS domain |
| FreightTender | Carrier waterfall — TMS execution domain |
| DockDoor / Appointment | Dock scheduling — TMS domain (though p44 can update ETAs) |
| ExceptionResolution | AIIO-driven resolution — uniquely TMS |
| ShippingForecast / CapacityTarget / TransportationPlan | Planning cascade — core TMS IP |
| LoadItem | Load composition — TMS planning domain |

---

## Transport mode coverage

| p44 Mode | TMS Modes | Mapping | Gap? |
|---|---|---|---|
| TRUCKLOAD | FTL | Bidirectional ✓ | — |
| LTL | LTL | Bidirectional ✓ | — |
| PARCEL | PARCEL, LAST_MILE | TMS→p44 ✓, p44→TMS one-way | LAST_MILE collapses to PARCEL on round-trip |
| OCEAN | FCL, LCL, BULK_OCEAN | TMS→p44 ✓ (all→OCEAN), p44→TMS defaults to FCL | p44 doesn't distinguish FCL/LCL; TMS needs to infer from identifiers or equipment |
| AIR | AIR_STD, AIR_EXPRESS, AIR_CHARTER | TMS→p44 ✓ (all→AIR), p44→TMS defaults to AIR_STD | Same loss of granularity on round-trip |
| RAIL | RAIL_CARLOAD, RAIL_UNIT | TMS→p44 ✓, p44→TMS defaults to RAIL_CARLOAD | p44 doesn't distinguish carload vs unit train |
| INTERMODAL | RAIL_INTERMODAL, INTERMODAL | Bidirectional ✓ | — |
| DRAYAGE | DRAYAGE | Bidirectional ✓ | — |

**Advice:** The granularity loss on round-trip (e.g., all three air modes collapse to AIR then back to AIR_STD) is acceptable because TMS is the system of record for mode. TMS tells p44 what mode to track; when data comes back, TMS already knows the original mode from its own `tms_shipment.mode` field. The only scenario where this matters is when p44 is the source of a new shipment (e.g., a shipment discovered via webhook that TMS didn't create) — in that case, the inferred mode is a best guess that the planner may need to correct.

---

## Summary — what to do

| Priority | Action | Effort | Value |
|---|---|---|---|
| High | Separate p44 vs Autonomy ETA confidence ranges | Small (schema change + data mapper update) | Prevents silent overwriting of conformal predictions; enables model comparison |
| High | Wire p44 appointment events to TMS Appointment entity | Small (webhook handler update) | Keeps DockSchedulingTRM in sync with carrier-confirmed times |
| Medium | Store p44 derivedStatus / health score on shipment | Small (2 columns + mapper update) | Gives ExceptionManagementTRM leading-indicator signal |
| Medium | Wire port intelligence to LaneProfile risk scores | Medium (periodic sync job + mapper integration) | Free signal improvement for DemandSensing + CapacityBuffer TRMs |
| Medium | Inbound document sync (BOL/POD from p44) | Medium (new sync service + API calls) | Shortens POD cycle; driver-signed receipts arrive faster |
| Low | Map p44 Order/Load to TMS Load | Medium (webhook handler + load reconciliation) | Only matters for multi-stop load visibility; individual shipment tracking works without it |
| None needed | Planning entities (forecast, capacity, rates, tenders, dock, commodities) | — | These are core TMS IP with no p44 counterpart by design |

The TMS data model is architecturally well-positioned relative to p44. The integration covers the full bidirectional mapping for tracking, identifiers, carriers, and events. The gaps above are refinements, not redesigns — they close feedback loops between p44's visibility data and TMS's planning/execution agents.
