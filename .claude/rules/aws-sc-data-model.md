# AWS Supply Chain Data Model compliance (TMS)

All data MUST use the AWS Supply Chain Data Model (SC DM) as the
canonical foundation. TMS extends the foundation with
transportation-specific entities.

The DAG network model is shared but nodes and edges have
transport-specific semantics.

## SC → TMS entity mapping (conceptual)

| SC planning entity | TMS equivalent | Notes |
|---|---|---|
| Product | Commodity / Freight Class | What's being shipped, not manufactured |
| Site (MANUFACTURER) | Origin / Shipper | Loading point |
| Site (INVENTORY) | Terminal / Cross-Dock / Yard | Intermediate handling |
| Site (MARKET_DEMAND) | Destination / Consignee | Delivery point |
| Site (MARKET_SUPPLY) | Carrier / Broker | Capacity provider |
| Transportation Lane | Lane | Shared — origin-destination pair with mode |
| Purchase Order | Shipment / Load | Unit of freight movement |
| Manufacturing Order | Consolidation / Deconsolidation | Combining/splitting loads |
| Transfer Order | Drayage / Intermodal Transfer | Movement between modes/terminals |
| BOM | Load Plan / Packing Spec | How freight fills equipment |
| Demand Plan | Shipping Demand Forecast | Expected freight volumes by lane |
| Supply Plan | Capacity Plan | Carrier capacity by lane/mode |
| MPS | Transportation Plan | Which loads move when, on what |
| Inventory Level | Yard/Dock Inventory | Trailers, containers at facility |
| ATP | Available Capacity to Promise | Carrier/lane capacity commitment |

This mapping is **conceptual** — code does NOT re-import SCP models
under TMS names. TMS has its own SQLAlchemy `Base` and independent
migrations. See [core-vs-product-placement.md](core-vs-product-placement.md).

## Transportation modes

- **Road**: FTL (Full Truckload), LTL (Less-than-Truckload), Parcel
- **Ocean**: FCL (Full Container), LCL (Less-than-Container), Bulk
- **Air**: Standard, Express, Charter
- **Rail**: Carload, Intermodal, Unit Train
- **Intermodal**: Combinations (truck-rail, truck-ocean, etc.)

## Key TMS entities (to be implemented)

- **Shipment** — unit of freight from origin to destination
- **Load** — physical grouping of shipments on equipment
- **Carrier** — transportation provider with rates, lanes, capacity
- **FreightRate** — rate per lane / mode / carrier with validity period
- **Equipment** — trailer, container, railcar types and availability
- **Appointment** — dock-door scheduling (pickup / delivery windows)
- **BOL** — Bill of Lading, legal shipping document
- **POD** — Proof of Delivery, confirmation record
- **Exception** — shipment exception (delay, damage, refused, rolled)

## Canonical-first rule

If a new entity is canonical — plausibly needed by SCP, CRM, WMS, or
Portfolio — it belongs in `Autonomy-Core/packages/data-model/`, not in
TMS. Use extensions only when necessary, documented as
`Extension: <reason>` in the docstring.
