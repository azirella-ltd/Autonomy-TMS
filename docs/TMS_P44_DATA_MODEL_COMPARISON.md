# TMS Data Model vs project44 Data Model — Comparison & Advice

**Created:** 2026-04-12
**Last verified:** 2026-04-30 (all six original gaps confirmed closed in code)
**Sister doc:** [TMS_DATA_MODEL.md](TMS_DATA_MODEL.md)

> **Status:** Integration is **complete** for the v1 scope. The six gaps
> originally identified on 2026-04-12 were all closed within the same
> week (commits `9658a424` + `77b8b925`); 2026-04-30 verification
> confirmed each in code. The "Gaps worth addressing" section is
> retained below as a **closed-gaps log** so the audit trail is
> readable, and the "Summary — what to do" table is updated to reflect
> the current state.

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

## Closed gaps (audit log — all addressed in the 2026-04-12 sprint)

> Each subsection retains the original gap description for context and
> appends a **Resolution** block citing where the fix landed. Verified
> in code 2026-04-30.

### 1. p44 Shipment Status model is richer than TMS consumes — ✅ CLOSED

**Gap (as identified 2026-04-12):** p44's status model is a nested object (`{ code, description, derivedStatus, health }`) with both a raw status code and a "derived" health assessment. TMS was flattening this to a single status string via `_map_p44_status()`, losing the `derivedStatus` and `health` score.

**Resolution (commit `9658a424`):** Added `p44_derived_status` and `p44_health_score` columns to `tms_shipment` ([`tms_entities.py:622-623`](../backend/app/models/tms_entities.py#L622-L623)). Mapper writes both at [`data_mapper.py:333-336`](../backend/app/integrations/project44/data_mapper.py#L333). The health score is now available to ExceptionManagementTRM as a leading-indicator signal.

### 2. p44 Order/Load model vs TMS Load model — ✅ CLOSED

**Gap (as identified 2026-04-12):** p44's v4 introduced Order and Load as first-class entities sitting above tracked shipments, but TMS's Load entity wasn't mapped to p44's `masterShipmentId`.

**Resolution (commit `77b8b925`):** Added `p44_master_shipment_id` column on `tms_shipment` ([`tms_entities.py:624`](../backend/app/models/tms_entities.py#L624)) plus `p44_shipment_id` on the Load entity ([`tms_entities.py:1287`](../backend/app/models/tms_entities.py#L1287)). Webhook handler reconciles `inventory.v1.load.upserted` events into TMS Load records.

### 3. p44 ETA confidence model — ✅ CLOSED

**Gap (as identified 2026-04-12):** p44's `estimatedDeliveryWindow` was overwriting Autonomy's conformal P10/P50/P90 in the same `eta_confidence` JSON column.

**Resolution (commit `9658a424`):** `eta_confidence` JSON now uses the namespaced shape — see column docstring at [`tms_entities.py:617`](../backend/app/models/tms_entities.py#L617):

```json
{
    "p44":       { "p10": "...", "p50": "...", "p90": "..." },
    "autonomy":  { "p10": "...", "p50": "...", "p90": "..." },
    "composite": { "p10": "...", "p50": "...", "p90": "...", "method": "ensemble" }
}
```

Mapper writes p44's range under the `p44` sub-key, leaving Autonomy's conformal layer untouched ([`data_mapper.py:345-350`](../backend/app/integrations/project44/data_mapper.py#L345)). The composite is what ShipmentTrackingTRM consumes; the split preserves audit trail and enables model-comparison analysis.

### 4. p44 Document API — ✅ CLOSED

**Gap (as identified 2026-04-12):** TMS's BillOfLading and ProofOfDelivery were TMS-authored only; p44's signed driver receipts (often arriving before the carrier's EDI) weren't being pulled.

**Resolution (commit `77b8b925`):** New [`tracking_service.py:415` `sync_documents_for_shipment()`](../backend/app/integrations/project44/tracking_service.py#L415) pulls p44 documents and creates BOL/POD records with `source="P44"`. Webhook handler invokes it on delivery events ([`webhook_handler.py:830`](../backend/app/integrations/project44/webhook_handler.py#L830)). POD cycle shortened by p44's driver-app pipeline.

### 5. p44 Port Intelligence ↔ TMS LaneProfile — ✅ CLOSED

**Gap (as identified 2026-04-12):** `from_p44_port_intelligence()` was returning ephemeral dicts that didn't write through to LaneProfile risk fields.

**Resolution (commit `77b8b925`):** New [`tracking_service.py:306` `sync_port_intelligence_to_lane_profiles()`](../backend/app/integrations/project44/tracking_service.py#L306) writes `lane.congestion_risk_score` ([line 394](../backend/app/integrations/project44/tracking_service.py#L394)) and `lane.disruption_frequency` ([line 401](../backend/app/integrations/project44/tracking_service.py#L401)) for ocean-leg lanes. Scheduled to run periodically via [`tms_extraction_jobs.py:84` `tms_port_intelligence_sync`](../backend/app/services/tms_extraction_jobs.py#L84). DemandSensingTRM and CapacityBufferTRM read these fields directly, so the signal-quality improvement flows through automatically.

### 6. p44 Appointment Update events — ✅ CLOSED

**Gap (as identified 2026-04-12):** `APPOINTMENT_SET` and `UPDATED_DELIVERY_APPT` events were being mapped to tracking events but not propagating to the TMS Appointment entity, leaving DockSchedulingTRM's view stale.

**Resolution (commit `77b8b925`):** Webhook handler now recognises both event types ([`webhook_handler.py:515`](../backend/app/integrations/project44/webhook_handler.py#L515)) and updates the matching Appointment's `scheduled_start` / `scheduled_end` ([lines 572-574](../backend/app/integrations/project44/webhook_handler.py#L572)). DockSchedulingTRM stays in sync with carrier-confirmed times.

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

## Summary — current state

| Item | Status (verified 2026-04-30) | Reference |
|---|---|---|
| Separate p44 vs Autonomy ETA confidence ranges | ✅ Closed | Gap #3 above |
| Wire p44 appointment events to TMS Appointment | ✅ Closed | Gap #6 above |
| Store p44 derivedStatus / health score on shipment | ✅ Closed | Gap #1 above |
| Wire port intelligence to LaneProfile risk scores | ✅ Closed | Gap #5 above |
| Inbound document sync (BOL/POD from p44) | ✅ Closed | Gap #4 above |
| Map p44 Order/Load to TMS Load | ✅ Closed | Gap #2 above |
| Planning entities (forecast, capacity, rates, tenders, dock, commodities) | n/a — by design | TMS IP, no p44 counterpart |

The TMS data model is architecturally well-positioned relative to p44. The integration covers the full bidirectional mapping for tracking, identifiers, carriers, events, status health, ETA dual-range, document sync, port intelligence, appointment updates, and load mapping. **No outstanding p44 integration gaps as of 2026-04-30.**

Future p44 work — when it arises — likely falls into one of: new event types as p44 adds them; mode-granularity round-trip refinements (e.g. distinguishing FCL/LCL on inbound shipments — see Transport mode coverage above); or new p44 product surfaces (Order Visibility, Inventory Visibility) that aren't yet in TMS scope. None of these are tracked as live work today.
