# DAG Logic and Master Node Types

## Master Node Types
Only four master node types exist and drive all routing logic:

- **Market Supply** — upstream source for the network.
- **Market Demand** — terminal sink where demand is measured.
- **Inventory** — storage / fulfillment (distributor, wholesaler, retailer, component supplier, DC, etc.).
- **Manufacturer** — transforms consumed items into produced items (requires BOM).

Each supply‑chain config node keeps its own **SC node type** (e.g., Distributor, Retailer) but must map to one of the above **master node types**. The master type is what the DAG and simulations use to determine allowed flows.

## How SC Node Types Map to Master Types
- Market Supply → Market Supply
- Market Demand → Market Demand
- All storage/flow roles (Distributor, Wholesaler, Retailer, Component Supplier, DC, etc.) → Inventory
- Manufacturers (including Bottle/Six‑Pack/Case/Plant) → Manufacturer

## DAG Construction
1) Nodes declare both their SC type and master type.
2) Lanes (edges) connect nodes; routing uses master types:
   - Sources must be Market Supply (or, for complex nets, Inventory acting as supply).
   - Sinks must include at least one Market Demand.
3) The resulting DAG can be viewed with either SC node types (human-friendly names) or master types (routing semantics). The Sankey diagram in the admin UI now locks onto each node’s DAG type to choose labels and column ordering, so the definitions above must stay in sync with the actual nodes persisted in the database.

## Items and BOMs
- **Market Demand nodes**: must specify which item they demand.
- **Manufacturer nodes**: must specify both produced item(s) and consumed item(s) via a Bill of Materials (BOM) mapping `produced_item_id -> {consumed_item_name: ratio}`.
- BOMs are stored on the manufacturer node attributes under `bill_of_materials`.
- Market Supply provides the consumed items at the top of the chain; downstream manufacturers/markets consume according to the BOM.

## Current SC Configs (from DB, demand-flow ordering)

### Default TBG
- Nodes (Node Name / DAG Type / master):

| Node Name       | DAG Type    | Master Type     |
|-----------------|-------------|-----------------|
| Market Demand   | market_demand | Market Demand |
| Retailer        | retailer    | Inventory       |
| Wholesaler      | wholesaler  | Inventory       |
| Distributor     | distributor | Inventory       |
| Factory         | factory     | Inventory       |
| Market Supply   | market_supply | Market Supply |

- Items: Market Demand item = Case; Market Supply item = Six-Pack.
- BOMs: Factory makes Case from Six-Pack (1:4) while using the Inventory master type.
- DAG (master): Market Demand → Retailer → Wholesaler → Distributor → Factory → Market Supply.

### Six-Pack TBG
- Nodes (Node Name / DAG Type / master):

| Node Name       | DAG Type      | Master Type     |
|-----------------|---------------|-----------------|
| Market Demand   | market_demand | Market Demand   |
| Retailer        | retailer      | Inventory       |
| Wholesaler      | wholesaler    | Inventory       |
| Distributor     | distributor   | Inventory       |
| Case Mfg        | case_mfg      | Manufacturer    |
| Six-Pack Mfg    | six_pack_mfg  | Manufacturer    |
| Market Supply   | market_supply | Market Supply   |

- Items: Case, Six-Pack, Bottle.
- BOMs: Six-Pack Manufacturer makes Six-Pack from Bottle (1:6); Case Manufacturer makes Case from Six-Pack (1:4). Market Supply provides Bottle.
- DAG (master): Market Demand → Retailer → Wholesaler → Distributor → Case Manufacturer → Six-Pack Manufacturer → Market Supply.

### Bottle TBG
- Nodes (Node Name / DAG Type / master):

| Node Name       | DAG Type      | Master Type     |
|-----------------|---------------|-----------------|
| Market Demand   | market_demand | Market Demand   |
| Retailer        | retailer      | Inventory       |
| Wholesaler      | wholesaler    | Inventory       |
| Distributor     | distributor   | Inventory       |
| Case Mfg        | case_mfg      | Manufacturer    |
| Six-Pack Mfg    | six_pack_mfg  | Manufacturer    |
| Bottle Mfg      | bottle_mfg    | Manufacturer    |
| Market Supply   | market_supply | Market Supply   |

- Items: Case, Six-Pack, Bottle, RawMaterials.
- BOMs: Bottle Manufacturer makes Bottle from RawMaterials (1:1); Six-Pack Manufacturer makes Six-Pack from Bottle (1:6); Case Manufacturer makes Case from Six-Pack (1:4). Market Supply provides RawMaterials.
- DAG (master): Market Demand → Retailer → Wholesaler → Distributor → Case Manufacturer → Six-Pack Manufacturer → Bottle Manufacturer → Market Supply.

### Complex_SC
- Nodes (SC/master): Market Supply/Market Supply; Component Suppliers/Inventory; Manufacturers/Manufacturer; DCs (Distributors)/Inventory; Market Demands/Market Demand.
- Items: FG-01 – FG-10. Plants (Manufacturers) consume component suppliers per item BOMs; Market Demand nodes demand each item.
- DAG (master): Market Demand → DCs (Inventory) → Manufacturers → Component Suppliers (Inventory) → Market Supply.

## Guidance for Correct Configs
- Ensure Distributor/Wholesaler/Retailer/Component Supplier/DC nodes always set `master_type=INVENTORY`.
- Ensure Manufacturer nodes define a BOM for every produced item, pairing the produced item with consumed item(s) and ratios.
- Market Supply nodes provide the upstream consumed item; Market Demand nodes specify the demanded item. 
