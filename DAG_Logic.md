# DAG Logic and Master Site Types

## Master Site Types
Only four master site types exist and drive all routing logic:

- **Market Supply** — upstream source for the network.
- **Market Demand** — terminal sink where demand is measured.
- **Inventory** — storage / fulfillment (distributor, wholesaler, retailer, component supplier, DC, etc.).
- **Manufacturer** — transforms consumed products into produced products (requires BOM).

Each supply‑chain config site keeps its own **SC site type** (e.g., Distributor, Retailer) but must map to one of the above **master site types**. The master type is what the DAG and simulations use to determine allowed flows.

## How SC Site Types Map to Master Types
- Market Supply → Market Supply
- Market Demand → Market Demand
- All storage/flow roles (Distributor, Wholesaler, Retailer, Component Supplier, DC, etc.) → Inventory
- Manufacturers (including Bottle/Six‑Pack/Case/Plant) → Manufacturer

## DAG Construction
1) Sites declare both their SC type and master type.
2) Transportation lanes (edges) connect sites; routing uses master types:
   - Sources must be Market Supply (or, for complex nets, Inventory acting as supply).
   - Sinks must include at least one Market Demand.
3) The resulting DAG can be viewed with either SC site types (human-friendly names) or master types (routing semantics). The Sankey diagram in the admin UI now locks onto each site's DAG type to choose labels and column ordering, so the definitions above must stay in sync with the actual sites persisted in the database.

## Products and BOMs
- **Market Demand sites**: must specify which product they demand.
- **Manufacturer sites**: must specify both produced product(s) and consumed product(s) via a Bill of Materials (BOM) mapping `produced_product_id -> {consumed_product_name: ratio}`.
- BOMs are stored on the manufacturer site attributes under `bill_of_materials`.
- Market Supply provides the consumed products at the top of the chain; downstream manufacturers/markets consume according to the BOM.

## Current SC Configs (from DB, demand-flow ordering)

### Default TBG
- Sites (Site Name / DAG Type / master):

| Site Name       | DAG Type    | Master Type     |
|-----------------|-------------|-----------------|
| Market Demand   | market_demand | Market Demand |
| Retailer        | retailer    | Inventory       |
| Wholesaler      | wholesaler  | Inventory       |
| Distributor     | distributor | Inventory       |
| Factory         | factory     | Inventory       |
| Market Supply   | market_supply | Market Supply |

- Products: Market Demand product = Case; Market Supply product = Six-Pack.
- BOMs: Factory makes Case from Six-Pack (1:4) while using the Inventory master type.
- DAG (master): Market Demand → Retailer → Wholesaler → Distributor → Factory → Market Supply.

### Six-Pack TBG
- Sites (Site Name / DAG Type / master):

| Site Name       | DAG Type      | Master Type     |
|-----------------|---------------|-----------------|
| Market Demand   | market_demand | Market Demand   |
| Retailer        | retailer      | Inventory       |
| Wholesaler      | wholesaler    | Inventory       |
| Distributor     | distributor   | Inventory       |
| Case Mfg        | case_mfg      | Manufacturer    |
| Six-Pack Mfg    | six_pack_mfg  | Manufacturer    |
| Market Supply   | market_supply | Market Supply   |

- Products: Case, Six-Pack, Bottle.
- BOMs: Six-Pack Manufacturer makes Six-Pack from Bottle (1:6); Case Manufacturer makes Case from Six-Pack (1:4). Market Supply provides Bottle.
- DAG (master): Market Demand → Retailer → Wholesaler → Distributor → Case Manufacturer → Six-Pack Manufacturer → Market Supply.

### Bottle TBG
- Sites (Site Name / DAG Type / master):

| Site Name       | DAG Type      | Master Type     |
|-----------------|---------------|-----------------|
| Market Demand   | market_demand | Market Demand   |
| Retailer        | retailer      | Inventory       |
| Wholesaler      | wholesaler    | Inventory       |
| Distributor     | distributor   | Inventory       |
| Case Mfg        | case_mfg      | Manufacturer    |
| Six-Pack Mfg    | six_pack_mfg  | Manufacturer    |
| Bottle Mfg      | bottle_mfg    | Manufacturer    |
| Market Supply   | market_supply | Market Supply   |

- Products: Case, Six-Pack, Bottle, RawMaterials.
- BOMs: Bottle Manufacturer makes Bottle from RawMaterials (1:1); Six-Pack Manufacturer makes Six-Pack from Bottle (1:6); Case Manufacturer makes Case from Six-Pack (1:4). Market Supply provides RawMaterials.
- DAG (master): Market Demand → Retailer → Wholesaler → Distributor → Case Manufacturer → Six-Pack Manufacturer → Bottle Manufacturer → Market Supply.

### Complex_SC
- Sites (SC/master): Market Supply/Market Supply; Component Suppliers/Inventory; Manufacturers/Manufacturer; DCs (Distributors)/Inventory; Market Demands/Market Demand.
- Products: FG-01 – FG-10. Plants (Manufacturers) consume component suppliers per product BOMs; Market Demand sites demand each product.
- DAG (master): Market Demand → DCs (Inventory) → Manufacturers → Component Suppliers (Inventory) → Market Supply.

## Guidance for Correct Configs
- Ensure Distributor/Wholesaler/Retailer/Component Supplier/DC sites always set `master_type=INVENTORY`.
- Ensure Manufacturer sites define a BOM for every produced product, pairing the produced product with consumed product(s) and ratios.
- Market Supply sites provide the upstream consumed product; Market Demand sites specify the demanded product. 
