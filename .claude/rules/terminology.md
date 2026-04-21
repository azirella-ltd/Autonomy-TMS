# Terminology (TMS)

Canonical cross-product terminology is in Autonomy-Core. Transport-plane
terminology and SC→TMS mapping below.

## SC → TMS term mapping

| SC term | TMS term | Context |
|---|---|---|
| Product | Commodity / Freight Class | What moves |
| Site | Location / Facility | Where it moves |
| node | location | Network topology |
| item | commodity | Freight classification |
| lane | lane | Shared — origin-destination pair |
| Purchase Order | Shipment | Freight movement unit |
| Manufacturing Order | Load Build | Load consolidation |
| Transfer Order | Intermodal Transfer | Mode change |
| Demand Plan | Shipping Forecast | Volume prediction |
| Supply Plan | Capacity Plan | Carrier availability |
| MPS | Transportation Plan | Execution schedule |
| ATP | Available Capacity to Promise | Lane capacity |
| BOM | Load Plan | Equipment utilisation spec |
| Safety Stock | Buffer Capacity | Reserve carrier capacity |
| Inventory Buffer | Yard Buffer | Equipment / trailer buffer at facility |
| Game | Scenario | Simulation |
| Group / `group_id` | Tenant / `tenant_id` | Organisation boundary |
| PENDING / ACCEPTED / AUTO_EXECUTED / EXPIRED | **ACTIONED** | AIIO state |
| REJECTED | **OVERRIDDEN** | AIIO state |

## `customer_id` vs `tenant_id`

- `customer_id` — **only** for trading partners (carriers, brokers,
  consignees) in the AWS SC DM sense.
- `tenant_id` — organisation boundary.

Mixing these is a bug.

## Planning hierarchy — use Strategic / Tactical / Operational / Execution

See [planning-hierarchy-terms.md](planning-hierarchy-terms.md). Canonical
names only — never "Tier N" or "Layer N" as planning-layer synonyms.

## AIIO states

See [aiio-model.md](aiio-model.md). Only ACTIONED / INFORMED /
INSPECTED / OVERRIDDEN.
