# ERP / TMS System Integration Architecture

**Created:** 2026-04-12
**Status:** Planning doc — no implementation yet
**Sister docs:**
- [TMS_DATA_MODEL.md](TMS_DATA_MODEL.md) — canonical entity reference
- [TMS_P44_DATA_MODEL_COMPARISON.md](TMS_P44_DATA_MODEL_COMPARISON.md) — visibility integration (p44)

## Purpose

Autonomy TMS doesn't replace SAP TM, Blue Yonder, or Oracle OTM — it sits alongside as the **AI decision layer** that consumes their operational data and feeds back optimized decisions via the AIIO governance pipeline.

```
┌─────────────────────┐     ┌──────────────────────┐
│  Customer's TMS      │     │  Autonomy TMS         │
│  (SAP TM, BY, OTM)  │────▶│  (AI Decision Layer)  │
│                      │◀────│                       │
│  System of Record    │     │  System of Intelligence│
│  for execution       │     │  for decisions         │
└─────────────────────┘     └──────────────────────┘
```

**Inbound** (TMS → Autonomy): shipments, loads, carriers, rates, appointments, exceptions, tracking events, historical execution data

**Outbound** (Autonomy → TMS): optimized carrier assignments, load builds, appointment recommendations, exception resolutions, capacity commitments — all via the AIIO governance pipeline

---

## Schema architecture: [ERP]-Core + [ERP]-SCP + [ERP]-TMS

### Why three layers (not two)

A customer who uses SAP has ONE SAP system. SAP's master data (Business Partners, Materials, Plants) is the SAME data whether SCP reads it (as suppliers for procurement) or TMS reads it (as carriers for freight). Extracting the same SAP table twice with two different mapping rules and two different staging tables creates:

- **Drift**: SCP's copy of a Business Partner diverges from TMS's copy when extraction schedules differ
- **Double configuration**: customer enters the same SAP credentials twice
- **Double maintenance**: field mapping changes have to be applied in two places

The three-layer pattern avoids all of this:

| Layer | What it contains | Where it lives |
|---|---|---|
| **[ERP]-Core** | Connection management, master data extraction (BP, Material, Plant → canonical entities), field mapping framework, staging patterns | `Autonomy-Core/packages/integrations/` |
| **[ERP]-SCP** | Manufacturing/planning-specific extraction (BOM, MRP, Production Orders, Demand Plans) | `Autonomy-SCP/backend/app/integrations/` |
| **[ERP]-TMS** | Freight/carrier-specific extraction (Freight Orders, Carrier Contracts, Rates, Appointments) | `Autonomy-TMS/backend/app/integrations/` |

This follows the same pattern as every other layer:

| Layer | Core (shared) | SCP | TMS |
|---|---|---|---|
| Data model | `azirella-data-model` | SCP extensions | TMS extensions |
| Frontend | `@azirella-ltd/autonomy-frontend` | SCP pages + types | TMS pages + types |
| Integrations | **ERP-Core** | **ERP-SCP** | **ERP-TMS** |

---

## Target TMS systems (priority order)

| System | Market position | Integration method | Why target it |
|---|---|---|---|
| **SAP TM** | #1 enterprise TMS (embedded in S/4HANA) | SAP Integration Suite / OData / IDoc / RFC | Largest installed base. SAP customers have budget and pain (SAP TM's AI is weak). |
| **Oracle OTM** | #2-3 enterprise | REST API / Integration Cloud | Huge in 3PL and multi-modal. Oracle's Redwood AI is aspirational, not shipped. |
| **Blue Yonder TMS** | #2-3 enterprise (ex-JDA) | REST API / EDI | Strong in retail/CPG logistics. Luminate platform still being built — AI gap is real. |
| **Manhattan Active TM** | Rising in mid-market+ | REST API (modern, well-documented) | Best API of the bunch. Natural partner, not competitor. |
| **MercuryGate** | Mid-market TMS | REST API / EDI | Strong in broker/3PL space. Simpler integration. |

**Priority: SAP TM first, Oracle OTM second.** SAP has the largest addressable market, and the codebase already has SAP integration patterns from the SCP fork.

---

## Data flow: what each integration extracts and injects

### Inbound: TMS → Autonomy (extraction)

| Data | Frequency | Method | Feeds which TRM |
|---|---|---|---|
| **Shipments** (active + historical) | Near-real-time or batch | API poll / webhook / EDI 214 | ShipmentTrackingTRM, ExceptionManagementTRM |
| **Loads** (planned, tendered, in-transit) | Near-real-time | API poll / webhook | LoadBuildTRM, FreightProcurementTRM |
| **Carriers** (master data, contracts, rates) | Daily/weekly batch | API / flat file | FreightProcurementTRM, BrokerRoutingTRM |
| **Freight rates** (contract + spot) | Daily batch | API / rate file import | FreightProcurementTRM |
| **Appointments** (scheduled, actual) | Near-real-time | API / EDI 204/214 | DockSchedulingTRM |
| **Exceptions** (delays, damages, refusals) | Real-time | Webhook / EDI 214 | ExceptionManagementTRM |
| **Historical execution data** (6-24 months) | One-time + incremental | Batch extract | All TRMs (training data for Powell RL) |
| **Network** (sites, lanes, equipment) | Weekly batch | API / config sync | CapacityPromiseTRM, EquipmentRepositionTRM |

### Outbound: Autonomy → TMS (decision injection)

| Decision | AIIO mode | Method | What happens in the TMS |
|---|---|---|---|
| **Carrier assignment** | AUTOMATE or INFORM | API call / EDI 204 | TMS tenders the load to the recommended carrier |
| **Load consolidation** | INSPECT | API + Decision Stream | Planner reviews in Autonomy, approves, TMS builds the load |
| **Appointment optimization** | AUTOMATE | API call | TMS reschedules dock appointments |
| **Exception resolution** | INSPECT | Decision Stream → API | Planner reviews agent's resolution, TMS executes |
| **Capacity commitment** | INFORM | Dashboard + API | TMS books capacity based on Autonomy's forecast |
| **Rate negotiation guidance** | INFORM | Dashboard only | No API — human uses analytics in rate negotiations |

---

## SAP-specific data mapping

### SAP-Core (shared master data, in Autonomy-Core)

One connection, one set of credentials, shared master data extraction.

| SAP Object | SAP Table / API | Canonical Entity | Why shared |
|---|---|---|---|
| Business Partner | LFA1 (vendor) + KNA1 (customer) | `TradingPartner` | A carrier IS a vendor. SCP sees them as suppliers, TMS sees them as carriers. Same row in SAP, same entity in canonical, different `tpartner_type`. |
| Material | MARA + MAKT | `Product` | SCP needs it for BOM/MRP. TMS needs it for commodity/freight class. Same master record. |
| Plant / Site | T001W + ADRC | `Site` | SCP sees it as a manufacturing site. TMS sees it as a pickup/delivery location. Same physical place. |
| Transportation Zone | TZONE | `TransportationLane` (partial) | Both products use lane definitions. |
| Incoterms | T685T | Reference data | Shared commercial terms. |
| Unit of Measure | T006 | Reference data | Shared. |

### SAP-SCP (planning-specific, in Autonomy-SCP)

| SAP Object | SAP Table / API | SCP Entity | Why SCP-only |
|---|---|---|---|
| Bill of Material | STPO / STAS | `ProductBom` | Manufacturing structure |
| Routing / Work Center | PLKO / CRHD | `ProductionProcess` | Production process |
| Production Order | AUFK / AFKO | `ManufacturingOrder` | Manufacturing execution |
| MRP Data | MDKP / MDTB | Demand/supply planning | Planning-specific |
| Purchase Order | EKKO / EKPO | `PurchaseOrder` | Procurement |
| Inventory | MARD / MARC | `InvLevel` | Inventory positions |

### SAP-TMS (freight-specific, in Autonomy-TMS)

| SAP Object | SAP Table / API | TMS Entity | Why TMS-only |
|---|---|---|---|
| Freight Order | VTTK / VTTS / API_FREIGHT_ORDER | `Shipment` + `Load` | Freight execution |
| Freight Unit | VTTK line items | `ShipmentLeg` | Multi-leg freight |
| Freight Booking | VFKK | `FreightTender` | Carrier tendering |
| Freight Cost | VFKP | `FreightRate` | Rate management |
| Carrier Master (extended) | LFA1 + transport flags | `Carrier` (extends TradingPartner) | Carrier-specific attributes beyond core |
| Scheduling Agreement | EKKO (SA doc type) | `CarrierContract` | Contract management |
| Delivery Document | LIKP / LIPS | `BillOfLading` / `ProofOfDelivery` | Shipping documents |
| Shipment Status | VTTK-STTRG | `TrackingEvent` | Status tracking |

### Overlap zone — entities that both products consume

| Entity | SCP reads it as | TMS reads it as | Resolution |
|---|---|---|---|
| **Purchase Order** | A procurement decision (PO_CREATION TRM) | A freight trigger (PO means something needs to ship) | **Core extracts PO.** SCP extends with MRP context. TMS reads the core PO to generate shipment demand. One extraction, two consumers. |
| **Delivery** | An outbound fulfillment signal | The starting point for a shipment | **Core extracts Delivery.** Same logic as PO. |
| **Business Partner (Carrier)** | SCP doesn't need carrier-specific fields | TMS needs SCAC, MC#, DOT#, equipment, insurance | **Core extracts base TradingPartner.** TMS adds carrier-specific enrichment via a second pass. This is the `Carrier` extension model already in the TMS data model. |

---

## Oracle OTM-specific data mapping

### Oracle-Core (shared master data)

| Oracle Object | Oracle API / Module | Canonical Entity |
|---|---|---|
| Suppliers | AP module | `TradingPartner` (tpartner_type='supplier') |
| Customers | AR module | `TradingPartner` (tpartner_type='customer') |
| Items | INV module | `Product` |
| Organizations / Sites | INV module | `Site` |

### Oracle-SCP (planning-specific)

| Oracle Object | Module | SCP Entity |
|---|---|---|
| Planning Data Sets | SCM Planning Cloud | Demand/supply planning |
| Demand Plans | SCM Planning Cloud | `Forecast` |
| Supply Plans | SCM Planning Cloud | `SupplyPlan` |
| Work Orders | Manufacturing Cloud | `ManufacturingOrder` |

### Oracle-TMS (freight-specific)

| Oracle Object | OTM API | TMS Entity |
|---|---|---|
| Shipments | OTM Shipment API | `Shipment` |
| Loads | OTM Load API | `Load` + `LoadItem` |
| Carriers | OTM Service Provider API | `Carrier` + `CarrierLane` |
| Rates | OTM Rate Offering API | `FreightRate` |
| Appointments | OTM Dock Scheduling | `Appointment` |
| Stops | OTM Stop API | `ShipmentLeg` |
| Exceptions | OTM Exception API | `ShipmentException` |

---

## Blue Yonder TMS-specific data mapping

Blue Yonder is TMS-only (no SCP-equivalent in the same product family), so the split is simpler: Core + TMS, no SCP layer.

| BY Object | BY API | TMS Entity |
|---|---|---|
| Order | Orders API | `Shipment` |
| Load | Loads API | `Load` + `LoadItem` |
| Carrier | Carriers API | `Carrier` + `CarrierLane` |
| Rate | Rates API | `FreightRate` |
| Appointment | Appointments API | `Appointment` |
| Stop | Stops API | `ShipmentLeg` |
| Exception | Exceptions API | `ShipmentException` |

---

## Repo layout

```
Autonomy-Core/
└── packages/
    ├── data-model/               ← Already exists
    ├── autonomy-frontend/        ← Already exists
    └── integrations/             ← NEW
        ├── core/
        │   ├── connection.py         ← Abstract connection (credentials, OAuth, health)
        │   ├── adapter.py            ← Abstract extraction/injection adapters
        │   ├── field_mapping.py      ← Configurable field mapping framework
        │   └── staging.py            ← Staging table pattern
        ├── sap/
        │   ├── connection.py         ← SAP-specific auth (RFC, OData, BTP)
        │   ├── master_data.py        ← BP, Material, Plant → canonical entities
        │   └── types.py              ← SAP type mappings
        ├── oracle/
        │   ├── connection.py         ← Oracle-specific auth (REST, Integration Cloud)
        │   ├── master_data.py        ← Supplier, Item, Org → canonical entities
        │   └── types.py
        └── blue_yonder/
            ├── connection.py
            ├── master_data.py
            └── types.py

Autonomy-SCP/backend/app/integrations/
├── sap/
│   ├── scp_extraction.py         ← BOM, MRP, ProdOrder extraction
│   └── scp_injection.py          ← Push planning decisions back
├── oracle/
│   ├── scp_extraction.py
│   └── scp_injection.py
└── ...

Autonomy-TMS/backend/app/integrations/
├── sap/
│   ├── tms_extraction.py         ← Freight Order, Carrier, Rate
│   └── tms_injection.py          ← Push carrier assignments, load builds
├── oracle/
│   ├── tms_extraction.py         ← OTM Shipments, Loads, Carriers
│   └── tms_injection.py
├── blue_yonder/
│   ├── tms_extraction.py
│   └── tms_injection.py
└── project44/                    ← Already exists (visibility, not TMS system)
    ├── connector.py
    ├── tracking_service.py
    ├── webhook_handler.py
    └── data_mapper.py
```

---

## Abstract adapter interfaces

```python
# Autonomy-Core/packages/integrations/core/adapter.py

class ERPMasterDataAdapter(ABC):
    """Shared master data extraction — one implementation per ERP vendor.
    
    Extracts master data that both SCP and TMS consume: trading partners,
    sites, products, lanes. One connection, one set of credentials.
    """
    
    @abstractmethod
    async def connect(self, config: Dict[str, Any]) -> None: ...
    
    @abstractmethod
    async def test_connection(self) -> Dict[str, Any]: ...
    
    @abstractmethod
    async def extract_trading_partners(
        self, since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]: ...
    
    @abstractmethod
    async def extract_sites(
        self, since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]: ...
    
    @abstractmethod
    async def extract_products(
        self, since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]: ...
    
    @abstractmethod
    async def extract_lanes(
        self, since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]: ...


class TMSExtractionAdapter(ABC):
    """TMS-specific extraction — one implementation per TMS vendor.
    
    Uses the shared master data adapter's connection. Extracts freight/
    carrier data that only TMS needs.
    """
    
    def __init__(self, master: ERPMasterDataAdapter):
        self.master = master  # Shares connection + master data
    
    @abstractmethod
    async def extract_shipments(
        self, since: datetime
    ) -> List[Dict[str, Any]]: ...
    
    @abstractmethod
    async def extract_loads(
        self, since: datetime
    ) -> List[Dict[str, Any]]: ...
    
    @abstractmethod
    async def extract_carriers(self) -> List[Dict[str, Any]]: ...
    
    @abstractmethod
    async def extract_rates(self) -> List[Dict[str, Any]]: ...
    
    @abstractmethod
    async def extract_appointments(
        self, since: datetime
    ) -> List[Dict[str, Any]]: ...
    
    @abstractmethod
    async def extract_exceptions(
        self, since: datetime
    ) -> List[Dict[str, Any]]: ...
    
    @abstractmethod
    async def push_decision(
        self, decision: Dict[str, Any]
    ) -> Dict[str, Any]: ...


class SCPExtractionAdapter(ABC):
    """SCP-specific extraction — one implementation per ERP vendor.
    
    Uses the shared master data adapter's connection. Extracts planning/
    manufacturing data that only SCP needs.
    """
    
    def __init__(self, master: ERPMasterDataAdapter):
        self.master = master
    
    @abstractmethod
    async def extract_boms(self) -> List[Dict[str, Any]]: ...
    
    @abstractmethod
    async def extract_production_orders(
        self, since: datetime
    ) -> List[Dict[str, Any]]: ...
    
    @abstractmethod
    async def extract_demand_plans(self) -> List[Dict[str, Any]]: ...
    
    @abstractmethod
    async def extract_inventory_levels(
        self, since: datetime
    ) -> List[Dict[str, Any]]: ...
    
    @abstractmethod
    async def push_decision(
        self, decision: Dict[str, Any]
    ) -> Dict[str, Any]: ...
```

---

## What already exists in the codebase

The SCP fork brought significant SAP integration infrastructure:

| File | What it does | Reusable for Core? |
|---|---|---|
| `integrations/sap/sap_atp_bridge.py` | ATP constraint bridge | SCP-specific |
| `integrations/mcp/adapters/sap_s4.py` | MCP adapter for S/4HANA | **Yes** — the connection pattern is reusable |
| `services/sap_staging_jobs.py` | Staging job orchestration | **Yes** — the staging pattern is reusable |
| `services/sap_staging_repository.py` | Staging table CRUD | **Yes** — the repository pattern is reusable |
| `services/sap_field_mapping_service.py` | Field mapping engine | **Yes** — the mapping framework is reusable |
| `services/sap_csv_exporter.py` | CSV export for SAP upload | SCP-specific (planning data) |
| `services/sap_config_builder.py` | Build SC config from SAP data | SCP-specific |
| `services/sap_data_staging_service.py` | Data staging orchestration | **Yes** — pattern is reusable |
| `services/sap_user_provisioning_service.py` | Provision users from SAP HR | **Yes** — user sync is shared |
| `models/sap_staging.py` | SAP staging tables | **Partially** — master data tables reusable, planning tables SCP-specific |
| `models/erp_connection.py` | ERP connection management | **Yes** — the connection model is vendor-agnostic |
| `models/erp_registry.py` | Multi-ERP registry | **Yes** — supports multiple ERP instances per tenant |
| `integrations/d365/` | Dynamics 365 integration | **Pattern reusable**, D365-specific code stays |
| `integrations/infor/` | Infor integration | **Pattern reusable**, Infor-specific code stays |
| `integrations/odoo/` | Odoo integration | **Pattern reusable**, Odoo-specific code stays |
| `integrations/b1/` | SAP Business One integration | **Pattern reusable**, B1-specific code stays |

**Key takeaway:** the staging table pattern, field mapping framework, connection management, and MCP adapter pattern are all reusable. The domain-specific extraction logic (what tables to read, what fields to map) is per-product.

---

## Implementation priority

| Priority | Work | Where | Effort |
|---|---|---|---|
| **1** | Extract reusable patterns (connection, staging, field mapping) from existing SAP SCP integration into `Autonomy-Core/packages/integrations/core/` | Autonomy-Core | 1-2 sessions |
| **2** | Implement `SAPMasterDataAdapter` in `packages/integrations/sap/` using existing SAP connection code | Autonomy-Core | 1-2 sessions |
| **3** | Implement `SAPTMExtractionAdapter` in `Autonomy-TMS/backend/app/integrations/sap/` | Autonomy-TMS | 2-3 sessions |
| **4** | Implement `SAPTMInjectionAdapter` (push decisions back to SAP TM) | Autonomy-TMS | 1-2 sessions |
| **5** | Implement `OracleMasterDataAdapter` + `OracleTMExtractionAdapter` | Autonomy-Core + TMS | 2-3 sessions |
| **6** | Implement `BlueYonderTMSAdapter` (simpler — REST-native, no Core split needed initially) | Autonomy-TMS | 1-2 sessions |

**Total realistic budget:** 8-14 sessions across all vendors. SAP is the biggest because of the RFC/IDoc/OData complexity. Oracle and Blue Yonder are REST-native and faster to implement.

---

## Relationship to p44

p44 is a **visibility platform**, not a TMS system. It sits orthogonally to the TMS integrations:

```
                    ┌─────────────┐
                    │  p44         │
                    │  (visibility)│
                    └──────┬──────┘
                           │ tracking events, ETA, exceptions
                           ▼
┌──────────┐      ┌─────────────────┐      ┌──────────┐
│ SAP TM   │─────▶│  Autonomy TMS   │◀─────│ Oracle   │
│ BY TMS   │◀─────│  (AI decisions) │─────▶│ OTM      │
│ Manhattan│      └─────────────────┘      └──────────┘
└──────────┘   shipments, loads,        shipments, loads,
               carriers, rates          carriers, rates
```

A customer might have SAP TM as their TMS system of record AND p44 for real-time visibility. Autonomy consumes from both: operational data from SAP TM, visibility data from p44. The TRMs correlate both signals (e.g., ExceptionManagementTRM uses p44's health score + SAP TM's shipment status to decide whether to escalate).

---

## Open questions

1. **Should the integration Core package be a separate Python package** (`azirella-integrations`) or a subdirectory of `azirella-data-model`? Recommendation: separate package — integrations have runtime dependencies (HTTP clients, OAuth, connection pools) that the data model shouldn't carry.

2. **How does EDI fit?** Many SAP TM integrations use EDI X12 (204/214/990/210) as the wire format rather than direct API calls. The adapter interface should support both API-based and EDI-based extraction/injection. EDI parsing/generation can be a shared utility in the Core package.

3. **MCP as the decision injection layer?** The existing `mcp/adapters/sap_s4.py` suggests MCP was planned as the bidirectional protocol. Should decision injection always go through MCP tools, or should the adapter also support direct API/IDoc push? Recommendation: MCP for structured tool calls, direct API for high-frequency real-time injection (e.g., tracking status updates).

4. **Multi-tenant multi-ERP?** A single tenant might use SAP for some divisions and Oracle for others. The ERP registry model (`erp_registry.py`) already supports this. The adapter interface should accept a connection config, not assume a single global connection.

5. **Historical data extraction for ML training** — the Powell TRM training pipeline needs 6-24 months of historical execution data. This is a one-time bulk extract that's much larger than the ongoing incremental sync. Should it be a separate adapter method (`extract_historical_execution()`) or just `extract_shipments(since=24_months_ago)`? Recommendation: separate method with batch/pagination support and progress reporting.
