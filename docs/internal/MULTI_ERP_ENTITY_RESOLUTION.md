# Multi-ERP Entity Resolution

When an Autonomy tenant operates more than one ERP — a manufacturer on SAP S/4HANA that acquired a company on Odoo, a distributor using D365 for North America and SAP for Europe, a CPG company with Odoo for contract manufacturing and SAP for internal plants — the same real-world products, vendors, customers, and sites exist under **different IDs across systems**.

This document covers the entity resolution problem, the current platform gaps, Bluecrux Axon's validated approach, and a proposed implementation strategy.

---

## 1. The Entity Resolution Problem

Five entity types need cross-system reconciliation:

| Entity | SAP ID | D365 ID | Odoo ID | Real World |
|--------|--------|---------|---------|------------|
| **Product** | MATNR `000000012345` | ItemId `D-ITEM-0042` | `product.product` id `789` | Same SKU on the shelf |
| **Vendor** | LIFNR `0000001000` | VendAccountNum `US-VEND-100` | `res.partner` id `42` (supplier=True) | Same company you buy from |
| **Customer** | KUNNR `0000002000` | CustAccount `CUST-NA-050` | `res.partner` id `55` (customer=True) | Same company you sell to |
| **Site** | WERKS `1000` | InventSiteId `SITE-CHI` | `stock.warehouse` id `3` | Same physical building |
| **Product hierarchy** | MATKL `001` / SPART `10` | ItemGroup `FG-BLDG` | `product.category` id `12` | Same logical grouping |

**Why this is hard**: There is no universal product ID standard adopted across ERPs. GTIN/EAN exists but is only populated ~60% of the time in practice (raw materials and intermediates rarely have GTINs). Internal IDs are arbitrary strings with no semantic overlap. Product descriptions are in different languages, abbreviation styles, and levels of detail.

---

## 2. Current Multi-ERP Support in Autonomy

The platform already has the **plumbing** for multi-ERP but lacks the **intelligence layer** for cross-system reconciliation.

**What works today**:

| Component | Multi-ERP Ready? | How |
|-----------|-----------------|-----|
| `ERPConnection` model | Yes | Multiple connections per tenant, different `erp_type` values |
| Staging schemas | Yes | Separate `sap_staging`, `d365_staging`, `odoo_staging` PostgreSQL schemas |
| `Product.external_identifiers` (JSON) | Partial | Can store SAP MATNR, GTIN, UPC, etc. on same record |
| `Product.source` / `TradingPartner.source` | Partial | Tracks which ERP provided the record |
| AWS SC entity model | Yes | Canonical data model is ERP-agnostic by design |

**What's missing**:

| Gap | Impact |
|-----|--------|
| **No cross-ERP entity mapping table** | Cannot say "SAP product MAT-12345 = Odoo product PROD-789 = the same real-world item" |
| **No `erp_connection_id` on SupplyChainConfig** | Cannot track which connection built which config |
| **No config merging logic** | Each ERP creates a separate SupplyChainConfig — no unified view |
| **No deduplication logic** | Same vendor in SAP (LIFNR "V001") and D365 (VendAccountNum "V001") creates two `TradingPartner` records |
| **No source metadata on external_identifiers** | JSON stores `{sap_material_number: "MAT-12345"}` but not which ERP instance it came from |
| **No fuzzy matching engine** | No way to discover that two records across ERPs represent the same entity |

---

## 3. Phase 0: Cross-ERP Field Equivalence (Prerequisite)

Before any entity or transaction matching can happen, the system must know that SAP's `MENGE` is D365's `PurchasedQuantity` is Odoo's `product_qty` — they all mean "ordered quantity." Without this field-level Rosetta Stone, the transaction matcher cannot compare quantities, dates, or IDs across systems.

Autonomy already has per-ERP field mapping services (SAP → AWS SC, D365 → AWS SC, Odoo → AWS SC). The cross-ERP equivalence is established **through the canonical AWS SC model**: if SAP `EKPO.MENGE` maps to `inbound_order_line.ordered_qty` and Odoo `purchase.order.line.product_qty` also maps to `inbound_order_line.ordered_qty`, then `MENGE ≡ product_qty` via the AWS SC bridge.

### 3.1 Existing Field Mapping Architecture

Each ERP already has a 3-tier mapping service:

| Tier | Method | Confidence | Source |
|------|--------|-----------|--------|
| **1. Exact** | Dictionary lookup: ERP field → (AWS SC entity, AWS SC field) | 1.0 | `SAP_TABLE_FIELD_MAPPINGS`, `D365_ENTITY_FIELD_MAPPINGS`, `ODOO_MODEL_FIELD_MAPPINGS` |
| **2. Pattern** | Regex on field names (e.g., `.*MENGE` → quantity) | 0.75 | `SAP_FIELD_PATTERNS`, `D365_FIELD_PATTERNS`, `ODOO_FIELD_PATTERNS` |
| **3. Fuzzy** | String similarity / AI suggestion | 0.30-0.60 | Runtime |

**Implementation files**:
- SAP: `backend/app/services/sap_field_mapping_service.py` (~27K lines, 54+ tables, ~95 entities)
- D365: `backend/app/integrations/d365/field_mapping.py` (361 lines, ~40 entities)
- Odoo: `backend/app/integrations/odoo/field_mapping.py` (431 lines, ~30 models)

### 3.2 Cross-ERP Field Equivalence Table (Transaction Fields)

This is the Rosetta Stone that enables transaction matching. Every row shows the same real-world concept expressed in three different ERP field names, all resolved through the canonical AWS SC model.

#### Purchase Orders

| Concept | SAP (EKKO/EKPO/EKET) | D365 (PurchaseOrderHeadersV2/LinesV2) | Odoo (purchase.order/.line) | AWS SC Field |
|---------|----------------------|---------------------------------------|----------------------------|--------------|
| PO number | `EKKO.EBELN` | `PurchaseOrderNumber` | `purchase.order.name` | `inbound_order.order_number` |
| Vendor | `EKKO.LIFNR` | `VendorAccountNumber` | `purchase.order.partner_id` | `trading_partner.id` |
| Order date | `EKKO.BEDAT` | `OrderDate` | `purchase.order.date_order` | `inbound_order.order_date` |
| Currency | `EKKO.WAERS` | `CurrencyCode` | `purchase.order.currency_id` | `company.currency` |
| Line number | `EKPO.EBELP` | `LineNumber` | (implicit) | `inbound_order_line.line_number` |
| Product | `EKPO.MATNR` | `ItemNumber` | `purchase.order.line.product_id` | `product.id` |
| Ordered qty | `EKPO.MENGE` | `PurchasedQuantity` | `purchase.order.line.product_qty` | `inbound_order_line.ordered_qty` |
| Unit price | `EKPO.NETPR` | `PurchasePrice` | `purchase.order.line.price_unit` | `inbound_order_line.unit_price` |
| Expected delivery | `EKET.EINDT` | `DeliveryDate` | `purchase.order.line.date_planned` | `inbound_order_line.expected_date` |
| Received qty | `EKET.WEMNG` | `ReceivedQuantity` | `purchase.order.line.qty_received` | `inbound_order_line.received_qty` |
| Ship-from site | `EKPO.WERKS` | `SiteId` | `purchase.order.picking_type_id` | `site.id` |

#### Sales Orders

| Concept | SAP (VBAK/VBAP/VBEP) | D365 (SalesOrderHeadersV2/LinesV2) | Odoo (sale.order/.line) | AWS SC Field |
|---------|----------------------|-------------------------------------|-------------------------|--------------|
| SO number | `VBAK.VBELN` | `SalesOrderNumber` | `sale.order.name` | `outbound_order.order_number` |
| Customer | `VBAK.KUNNR` | `CustomerAccountNumber` | `sale.order.partner_id` | `trading_partner.id` |
| Order date | `VBAK.ERDAT` | `OrderDate` | `sale.order.date_order` | `outbound_order.order_date` |
| Requested date | `VBAK.VDATU` | `RequestedShipDate` | `sale.order.commitment_date` | `outbound_order.requested_delivery_date` |
| Product | `VBAP.MATNR` | `ItemNumber` | `sale.order.line.product_id` | `product.id` |
| Ordered qty | `VBAP.KWMENG` | `OrderedSalesQuantity` | `sale.order.line.product_uom_qty` | `outbound_order_line.ordered_qty` |
| Delivered qty | `VBEP.LMENG` | `DeliveredQuantity` | `sale.order.line.qty_delivered` | `outbound_order_line.delivered_qty` |
| Unit price | `VBAP.NETPR` | `SalesPrice` | `sale.order.line.price_unit` | `outbound_order_line.unit_price` |
| Ship-from site | `VBAP.WERKS` | `SiteId` | `sale.order.warehouse_id` | `site.id` |

#### Shipments / Deliveries

| Concept | SAP (LIKP/LIPS) | D365 (Packing Slip) | Odoo (stock.picking/.move) | AWS SC Field |
|---------|-----------------|---------------------|----------------------------|--------------|
| Shipment ID | `LIKP.VBELN` | Packing slip number | `stock.picking.name` | `shipment.shipment_number` |
| Actual ship date | `LIKP.WADAT_IST` | Ship date | `stock.picking.date_done` | `shipment.actual_ship_date` |
| Product | `LIPS.MATNR` | `ItemNumber` | `stock.move.product_id` | `product.id` |
| Actual qty | `LIPS.LFIMG` | Shipped qty | `stock.move.quantity` | `shipment_line.actual_qty` |
| Source order | `LIPS.VGBEL` | SO reference | `stock.move.origin` | `shipment.source_order_id` |
| Source site | `LIKP.VSTEL` | Ship-from warehouse | `stock.picking.location_id` | `site.id` (from) |
| Dest site | `LIKP.KUNAG` | Ship-to warehouse | `stock.picking.location_dest_id` | `site.id` (to) |

#### Goods Receipts / Inventory

| Concept | SAP (MSEG) | D365 (InventOnHand) | Odoo (stock.quant/.move) | AWS SC Field |
|---------|------------|---------------------|--------------------------|--------------|
| Product | `MSEG.MATNR` | `ItemNumber` | `stock.quant.product_id` | `product.id` |
| Quantity | `MSEG.MENGE` | `PhysicalOnHandQuantity` | `stock.quant.quantity` | `inv_level.on_hand_qty` |
| Site | `MSEG.WERKS` | `WarehouseId` | `stock.quant.location_id` | `site.id` |
| PO reference | `MSEG.EBELN` | PO FK | `stock.move.origin` | `inv_level.po_number` |
| Movement type | `MSEG.BWART` | Journal type | `stock.move.picking_type_id` | (routing) |
| Vendor | `MSEG.LIFNR` | Vendor FK | (via picking partner) | `trading_partner.id` |

#### Manufacturing Orders

| Concept | SAP (AUFK/AFKO/AFPO) | D365 (ProductionOrderHeaders) | Odoo (mrp.production) | AWS SC Field |
|---------|----------------------|-------------------------------|----------------------|--------------|
| MO number | `AUFK.AUFNR` | `ProductionOrderNumber` | `mrp.production.name` | `production_order.order_number` |
| Product | `AFKO.PLNBEZ` | `ItemNumber` | `mrp.production.product_id` | `product.id` |
| Planned qty | `AFKO.GAMNG` | `ProductionQuantity` | `mrp.production.product_qty` | `production_order.planned_qty` |
| Actual qty | `AFPO.WEMNG` | Completed qty | `mrp.production.qty_produced` | `production_order.actual_qty` |
| Start date | `AFKO.GSTRS` | `ScheduledStartDate` | `mrp.production.date_start` | `production_order.planned_start` |
| End date | `AFKO.GLTRP` | `ScheduledEndDate` | `mrp.production.date_finished` | `production_order.planned_end` |
| Site | `AUFK.WERKS` | `SiteId` | `mrp.production.location_src_id` | `site.id` |
| Status | `AUFK.ASTATUS` | `ProductionStatus` | `mrp.production.state` | `production_order.order_status` |
| BOM | `AFKO.STLNR` | BOM FK | `mrp.production.bom_id` | `product_bom.id` |

### 3.3 Field Name Pattern Equivalence

For extension fields or custom fields not in the exact mapping dictionaries, regex patterns provide cross-ERP inference:

| Concept | SAP Pattern | D365 Pattern | Odoo Pattern |
|---------|-------------|-------------|--------------|
| Quantity | `.*MENGE\|.*MENG` | `.*Quantity\|.*Qty` | `.*qty\|.*quantity` |
| Price | `.*PREIS\|.*PREI` | `.*Price\|.*Cost` | `.*price\|.*cost` |
| Date | `.*DATUM\|.*DAT` | `.*Date\|.*DateTime` | `.*date\|.*_date` |
| Site | `.*WERKS` | `.*SiteId` | `warehouse_id\|location_id` |
| Product | `.*MATNR` | `.*ItemNumber\|.*ProductNumber` | `product_id\|product_tmpl_id` |
| Order ID | `.*EBELN` (PO) / `.*VBELN` (SO) / `.*AUFNR` (MO) | `.*OrderNumber` | `order_id\|name` (contextual) |
| Vendor | `.*LIFNR` | `.*VendorAccount` | `partner_id` (supplier ctx) |
| Customer | `.*KUNNR` | `.*CustomerAccount` | `partner_id` (customer ctx) |

### 3.4 How Field Equivalence Enables Transaction Matching

With the field equivalence table established, the transaction matcher knows:

1. **What to compare**: SAP `EKPO.MENGE` and Odoo `purchase.order.line.product_qty` are both "ordered quantity" — compare them numerically
2. **How to compare**: SAP `EKKO.BEDAT` and Odoo `purchase.order.date_order` are both "order date" — compare them as dates with ±N day tolerance
3. **What links to what**: SAP `EKPO.MATNR` and Odoo `purchase.order.line.product_id` both reference the product — if the transaction matches, these product IDs are equivalent
4. **What's a key vs. a value**: SAP `EKKO.EBELN` and Odoo `purchase.order.name` are both order identifiers (match keys), while `MENGE`/`product_qty` are comparison values

**The resolution pipeline**:

```
Phase 0: Field Equivalence (this section)
  SAP EKPO.MENGE = D365 PurchasedQuantity = Odoo product_qty
  (resolved via AWS SC canonical model)
         │
         ▼
Phase 1: Master Data Matching (Section 4, Tiers 1-2)
  GTIN/EAN/DUNS exact match → resolves ~40-55% of entities
         │
         ▼
Phase 2: Transaction Matching (Section 4, Tier 3)
  Uses field equivalence to compare PO↔SO, shipment↔receipt
  across ERPs → resolves ~30-40% more
         │
         ▼
Phase 3: Description Matching (Section 4, Tier 4)
  TF-IDF + edit distance on product names → resolves ~10-15%
         │
         ▼
Phase 4: Human Confirmation (Section 4, Tier 5)
  UI presents remaining candidates → resolves final ~5-10%
```

### 3.5 Value Normalization

Even after field equivalence is established, the same value can be represented differently across ERPs:

| Value Type | SAP | D365 | Odoo | Normalization |
|-----------|-----|------|------|---------------|
| **Product ID** | Zero-padded 18-char (`000000000012345`) | Alphanumeric (`D-ITEM-0042`) | Integer (`789`) | Strip leading zeros, compare as string |
| **Vendor ID** | Zero-padded 10-char (`0000001000`) | Alphanumeric (`US-VEND-100`) | Integer FK + name | Cannot normalize — requires entity resolution |
| **Date** | `YYYYMMDD` string or SAP internal | ISO 8601 datetime | Python datetime / string | Parse to UTC date |
| **Quantity** | Decimal with SAP UOM (`MEINS`) | Decimal with UOM symbol | Decimal with Odoo UOM record | Convert to base UOM |
| **Currency** | ISO 4217 3-char (`USD`, `EUR`) | ISO 4217 3-char | Odoo currency record (name = ISO) | Already normalized |
| **Status** | Numeric codes (`01`, `02`, etc.) via TJ02T table | English strings (`Confirmed`, `Received`) | Python enum strings (`draft`, `done`) | Map to canonical enum |

**Unit of Measure normalization** is critical for quantity comparison. SAP uses `MEINS` (T006), D365 uses `InventoryUnitSymbol`, Odoo uses `uom.uom`. The AWS SC model uses `base_uom` as the canonical field. All quantities must be converted to the product's base UOM before cross-ERP comparison.

---

## 4. Bluecrux Axon: Validated Approach to Transaction-Driven Entity Resolution

**Bluecrux** (Aalst, Belgium, ~250 employees, ~$50M revenue) built **Axon**, a graph-based digital supply chain twin used by Sanofi (60 manufacturing sites, 200+ DCs), Johnson & Johnson, GSK, Roche, Bridgestone, and AkzoNobel. Recognized as a Representative Vendor in Gartner's Market Guide for Analytics and Decision Intelligence Platforms in Supply Chain.

### 4.1 Core Insight: Match Transactions, Not Master Data

**Traditional MDM approach** (fails at scale):
```
SAP Product "MAT-12345" (description: "Paracetamol 500mg Tab")
     ↔ fuzzy string match ↔
D365 Product "ITEM-0042" (description: "PARA-500MG-TAB")
     → 78% confidence — is this right? Maybe. Maybe not.
```

**Axon's transaction-driven approach** (works):
```
SAP: Shipment #SH-2024-001
  - From: Plant Frankfurt (WERKS 1000)
  - To: DC Rotterdam
  - Product: MAT-12345
  - Qty: 10,000 units
  - Ship date: 2026-03-15

D365: Goods Receipt #GR-44892
  - At: Warehouse NL-RTD-01
  - From: Supplier DE-FRA
  - Product: ITEM-0042
  - Qty: 10,000 units
  - Receipt date: 2026-03-17

→ Temporal match (2 days = typical Frankfurt→Rotterdam transit)
→ Quantity match (exact)
→ Location match (Frankfurt→Rotterdam in both)
→ Therefore: MAT-12345 = ITEM-0042 (99.2% confidence)
→ Therefore: Plant Frankfurt (WERKS 1000) = Warehouse NL-RTD-01's supplier
```

### 4.2 Transaction Matching Dimensions

| Dimension | Weight | Tolerance |
|-----------|--------|-----------|
| **Quantity** | High | ±2% (yield/scrap allowance) |
| **Date** | High | ±N days (expected transit time for the lane) |
| **Location pair** | High | Shipping-from ↔ receiving-at must be plausible |
| **Material flow direction** | Medium | Must follow DAG topology (upstream → downstream) |
| **BOM ratio** | Medium | 1000 kg raw → 950 units finished (if BOM known) |
| **Value/price** | Low | Currency conversion, transfer pricing make this noisy |
| **Description** | Low | Supplementary signal only, not primary |

### 4.3 Key Innovations

1. **Object-centric process mining** (van der Aalst methodology): Traces the physical object (material batch) across systems rather than tracing the process within one system. The batch doesn't care what ERP it's in.

2. **Anonymous inventory linking**: At warehouses, there's no shared transaction ID between goods receipt and goods issue. Axon uses fuzzy matching on quantity + timing + location to infer "these 500 units received Monday are the same 480 units picked Wednesday."

3. **BOM derivation from transactions**: Instead of trusting design BOMs in master data, Axon discovers actual BOMs from production records — "Factory-A consistently consumes 4.2 kg of Raw-X per unit of Finished-Y" even if the BOM says 4.0 kg.

4. **Self-maintaining master data**: Once entities are linked, Axon continuously compares planning parameters (lead times, yields, capacities) against actual observed performance and proposes updates.

### 4.4 Axon Architecture

- **Platform**: Enterprise SaaS on Microsoft Azure (Synapse/Databricks, Scala/PySpark)
- **Core engine**: Axon PME (Process Mining Engine) — proprietary, graph-based
- **Data model**: Proprietary common ontology (graph, not relational-first)
- **AI/ML**: Hybrid rule-based + ML for fuzzy matching, progressive accuracy improvement
- **Scale**: Sanofi runs it across 60+ sites, 200+ DCs, 23,000 users
- **Pricing**: Not public; estimated ~$200K-$1M+/yr enterprise SaaS

---

## 5. Inter-Company Partner Detection (Sites Masquerading as Vendors/Customers)

A core challenge in multi-ERP tenants: **vendors and customers in one ERP may actually be internal sites managed by another ERP**. When Plant A (on SAP) ships to DC B (on Odoo), SAP has DC B as a "customer" and Odoo has Plant A as a "vendor" — but both are internal sites of the same company.

This must be detected **before** entity resolution, because it changes the DAG topology: an inter-company lane is a `transfer` (site→site), not a `buy` (partner→site) or `sell` (site→partner).

### 5.1 How Each ERP Represents Internal Partners

Each ERP has **native flags** that identify inter-company partners — these are definitive signals available during Phase 1 staging:

**SAP — Plant-as-Vendor via T024W**:
```
Table T024W: Purchasing org → Plant → Vendor mapping
  T024W.LIFNR = the vendor number assigned to an internal plant
  T024W.WERKS = the plant code

Detection: JOIN LFA1 ON LFA1.LIFNR = T024W.LIFNR
  → If this join succeeds, the vendor IS an internal plant

Additional signals:
  LFA1.KTOKK (account group) = 'ICVN' or similar IC account group
  LFA1.KONZS / KNA1.KONZS (corporate group key) matches own company
  FI field RASSC (trading partner) on GL documents
```

**D365 — Explicit boolean flag**:
```
CustTable.InterCompanyTradingPartner = 1  (boolean)
VendTable.InterCompanyTradingPartner = 1  (boolean)

Detection: trivial — the flag is explicit on both customer and vendor records.

Additional:
  InterCompanyTradingRelationship table defines the legal entity pairs
  CustGroup / VendGroup = 'IC' (conventional grouping)
```

**Odoo — Company IS a Partner**:
```
Every res.company record has a partner_id FK to res.partner.
If sale.order.partner_id == any res.company.partner_id → inter-company sale
If purchase.order.partner_id == any res.company.partner_id → inter-company purchase

Detection:
  internal_partner_ids = env['res.company'].search([]).mapped('partner_id.id')
  is_internal = partner.id in internal_partner_ids
```

### 5.2 Detection Tiers for Cross-ERP Scenarios

Within a single ERP, the native flags above are definitive. But when Company A is on SAP and Company B is on Odoo, **neither ERP knows the other exists**. SAP sees Company B as a regular external customer; Odoo sees Company A as a regular external vendor.

Detection must use cross-system signals:

| Tier | Signal | Source | Confidence |
|------|--------|--------|-----------|
| **1. ERP-native flag** | `T024W.LIFNR` (SAP), `InterCompanyTradingPartner` (D365), `res.company.partner_id` (Odoo) | ERP master data in staging | 1.0 |
| **2. Tax ID / VAT match** | Vendor's `LFA1.STCD1` (SAP) or `res.partner.vat` (Odoo) matches a known tenant company Tax ID | Staging cross-reference | 0.90 |
| **3. DUNS tree lookup** | Vendor's DUNS ultimate parent matches tenant's parent DUNS | D&B API or `external_identifiers` | 0.85 |
| **4. GLN prefix match** | Vendor's GLN shares prefix block with tenant's GLN range | `external_identifiers` | 0.80 |
| **5. Address co-location** | Vendor's address matches a known internal site address within same postal code | Staging address fields | 0.65 |
| **6. Name containment** | Vendor name contains the parent company name (e.g., vendor "ACME Europe GmbH" for parent "ACME Corp") | Fuzzy string match | 0.55 |

### 5.3 TradingPartner Model Extension

The current `TradingPartner` model has no inter-company fields. Add:

```sql
-- Alembic migration: add inter-company detection columns to trading_partners
-- PostgreSQL (Autonomy's database)

ALTER TABLE trading_partners
    ADD COLUMN is_intercompany BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN linked_site_id  INTEGER REFERENCES site(id) ON DELETE SET NULL,
    ADD COLUMN linked_config_id INTEGER REFERENCES supply_chain_configs(id) ON DELETE SET NULL,
    ADD COLUMN detection_method VARCHAR(50),    -- erp_native, tax_id_match, duns_tree,
                                                -- gln_prefix, address_match, name_match,
                                                -- transaction_match, human_confirmed
    ADD COLUMN detection_confidence FLOAT,       -- 0.0-1.0
    ADD COLUMN detection_evidence JSONB;         -- supporting data (tax IDs matched, etc.)

CREATE INDEX idx_tp_intercompany ON trading_partners(company_id)
    WHERE is_intercompany = TRUE;

COMMENT ON COLUMN trading_partners.is_intercompany IS
    'TRUE when this vendor/customer is actually an internal site in another ERP';
COMMENT ON COLUMN trading_partners.linked_site_id IS
    'FK to the internal Site record this partner represents (NULL until resolved)';
COMMENT ON COLUMN trading_partners.linked_config_id IS
    'FK to the SupplyChainConfig containing the linked site';
```

### 5.4 Detection During Config Build

Each config builder runs inter-company detection **after** sites and partners are created but **before** lanes are finalized:

```python
class InterCompanyDetector:
    """
    Detect trading partners that are actually internal sites.
    Runs during provisioning, after all ERPs have been staged.
    """

    async def detect(self, tenant_id: int) -> List[InterCompanyMatch]:
        # 1. Collect all internal sites across all configs for this tenant
        all_sites = await self._get_all_tenant_sites(tenant_id)
        site_tax_ids = {s.company.tax_id: s for s in all_sites if s.company}
        site_addresses = {(s.latitude, s.longitude): s for s in all_sites
                          if s.latitude and s.longitude}

        # 2. For each trading partner, check detection tiers
        partners = await self._get_all_tenant_partners(tenant_id)
        matches = []

        for partner in partners:
            # Tier 1: ERP-native flag (already set during staging)
            if partner.external_identifiers.get('erp_intercompany_flag'):
                matches.append(InterCompanyMatch(
                    partner=partner, confidence=1.0,
                    method='erp_native',
                    evidence={'flag': 'erp_intercompany_flag'}))
                continue

            # Tier 2: Tax ID / VAT match
            partner_tax_id = (partner.external_identifiers.get('vat_id')
                              or partner.external_identifiers.get('tax_id'))
            if partner_tax_id and partner_tax_id in site_tax_ids:
                linked_site = site_tax_ids[partner_tax_id]
                matches.append(InterCompanyMatch(
                    partner=partner, linked_site=linked_site,
                    confidence=0.90, method='tax_id_match',
                    evidence={'matched_tax_id': partner_tax_id}))
                continue

            # Tier 3: DUNS tree
            partner_duns = partner.duns_number
            if partner_duns:
                parent_duns = await self._lookup_duns_parent(partner_duns)
                if parent_duns in tenant_duns_set:
                    matches.append(InterCompanyMatch(
                        partner=partner, confidence=0.85,
                        method='duns_tree',
                        evidence={'partner_duns': partner_duns,
                                  'parent_duns': parent_duns}))
                    continue

            # Tier 4-6: GLN prefix, address proximity, name containment
            # ... (similar pattern, decreasing confidence)

        return matches
```

### 5.5 Lane Reclassification

When a partner is identified as inter-company and linked to a site, the lane topology changes:

```
BEFORE detection:
  Lane: from_partner_id=Vendor_42 → to_site_id=DC_Chicago
  Type: inbound (buy)
  Sourcing rule: buy from external vendor

AFTER detection (Vendor_42 = internal Plant Frankfurt):
  Lane: from_site_id=Plant_Frankfurt → to_site_id=DC_Chicago
  Type: transfer (internal)
  Sourcing rule: transfer from internal site
```

This reclassification is critical for:
- **DAG topology**: Internal transfers use different TRM agents (TO Execution, not PO Creation)
- **Inventory planning**: Internal sources have different lead time distributions than external vendors
- **Cost modeling**: Transfer pricing vs. vendor pricing
- **Capacity planning**: Internal sources have known capacity constraints

---

## 6. Proposed Entity Resolution Strategy for Autonomy

### 6.1 Six-Tier Matching Strategy

Ordered by reliability — apply each tier in sequence:

| Tier | Method | Confidence | Coverage Estimate |
|------|--------|-----------|-------------------|
| **0. Inter-company detection** | ERP-native flags, Tax ID, DUNS tree (Section 5) | 0.55-1.0 | ~5-15% of partners are internal |
| **1. Global ID exact** | GTIN, EAN, UPC, DUNS, GLN, LEI | 1.0 | ~30-40% of finished goods, ~5% of raw materials |
| **2. Cross-reference exact** | Customer part number, vendor material number, INFO records | 0.95 | ~10-15% additional |
| **3. Transaction fuzzy** | PO↔SO / shipment↔receipt matching on qty + date + location | 0.70-0.99 | ~30-40% additional |
| **4. Description fuzzy** | TF-IDF + edit distance on product descriptions | 0.30-0.80 | ~10-15% additional |
| **5. Human confirmation** | UI presents candidates for manual review | 1.0 | Remaining ~5-10% |

### 6.2 Database Schema (PostgreSQL)

```sql
-- PostgreSQL (Autonomy uses PostgreSQL exclusively, never SQLite)

CREATE TABLE erp_entity_mapping (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- What entity type
    entity_type     VARCHAR(50) NOT NULL,  -- product, trading_partner, site, product_hierarchy

    -- The canonical Autonomy/AWS SC record
    canonical_id    VARCHAR(100) NOT NULL,  -- Product.id, TradingPartner.id, Site.id

    -- The ERP-specific record
    erp_connection_id INTEGER NOT NULL REFERENCES erp_connections(id),
    erp_entity_id     VARCHAR(200) NOT NULL,  -- MATNR, ItemId, product.product id
    erp_entity_name   VARCHAR(500),           -- Human-readable description from ERP

    -- Match quality
    match_method    VARCHAR(50) NOT NULL,     -- gtin_exact, duns_exact, transaction_fuzzy,
                                              -- description_fuzzy, human_confirmed,
                                              -- intercompany_native, tax_id_match
    match_confidence DOUBLE PRECISION NOT NULL CHECK (match_confidence BETWEEN 0.0 AND 1.0),
    match_evidence  JSONB DEFAULT '{}',       -- Supporting evidence (transaction IDs, scores)

    -- Lifecycle
    status          VARCHAR(20) NOT NULL DEFAULT 'active',  -- active, superseded, rejected
    confirmed_by    INTEGER REFERENCES users(id),           -- NULL = auto-matched
    confirmed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_erm_erp_entity
        UNIQUE(tenant_id, entity_type, erp_connection_id, erp_entity_id)
);

CREATE INDEX idx_erm_canonical
    ON erp_entity_mapping(tenant_id, entity_type, canonical_id);
CREATE INDEX idx_erm_erp_lookup
    ON erp_entity_mapping(tenant_id, erp_connection_id, entity_type);
CREATE INDEX idx_erm_unconfirmed
    ON erp_entity_mapping(tenant_id, match_confidence)
    WHERE confirmed_by IS NULL AND match_confidence < 0.90;
```

### 6.3 Transaction Matching Algorithm

```python
class TransactionMatcher:
    """
    Match inter-company transactions across ERPs to discover
    entity equivalences. Inspired by Bluecrux Axon's approach.

    Prerequisite: Phase 0 field equivalence (Section 3) must be
    established so the matcher knows that SAP EKPO.MENGE = Odoo
    purchase.order.line.product_qty = AWS SC inbound_order_line.ordered_qty.
    """

    def match_shipments(self, tenant_id: int) -> List[EntityMatch]:
        """
        For each outbound shipment in ERP-A staging, find the
        corresponding inbound receipt in ERP-B staging:
        - quantity (±2% tolerance for yield/scrap)
        - date (±N days based on expected transit time)
        - location pair (shipping site → receiving site)
        """

    def match_po_so_pairs(self, tenant_id: int) -> List[EntityMatch]:
        """
        Match purchase orders in ERP-A against sales orders in ERP-B
        for inter-company transactions:
        - PO date ≈ SO date (±3 days)
        - PO qty = SO qty (exact or ±rounding)
        - PO vendor = SO company (if site mapping exists)
        - PO unit price ≈ SO unit price (±currency conversion)
        """

    def derive_product_mapping(self, matched_txns: List) -> List[EntityMatch]:
        """
        From matched transactions, derive product equivalences.
        Confidence scales with evidence volume:
          1 match → 0.70, 2-3 → 0.80, 4-9 → 0.90, 10+ → 0.95
        """

    def derive_site_mapping(self, matched_txns: List) -> List[EntityMatch]:
        """
        From matched transactions, derive site equivalences:
        - Ship-from in ERP-A = the vendor identity in ERP-B
        - Receive-at in ERP-B = the customer identity in ERP-A
        """
```

**Confidence scaling based on evidence volume**:

| Matching Transactions | Product Confidence | Site Confidence |
|----------------------|-------------------|-----------------|
| 1 | 0.70 | 0.75 |
| 2-3 | 0.80 | 0.85 |
| 4-9 | 0.90 | 0.92 |
| 10+ | 0.95 | 0.97 |
| + GTIN/DUNS match | 1.00 | 1.00 |

### 6.4 Product Hierarchy Reconciliation

Product hierarchies are the hardest entity to reconcile because they are **arbitrary organizational decisions**, not physical reality. SAP uses MATKL + SPART + PRODH. D365 uses Item Group + Item Model Group. Odoo uses `product.category` with arbitrary nesting.

**Approach**: Bottom-up from product mappings, not top-down from hierarchy matching.

1. Resolve individual products across ERPs (Tiers 0-5 above)
2. For each resolved product, collect its hierarchy assignments from each ERP
3. Build cross-hierarchy mapping from product membership overlap (if 85% of products in SAP MATKL "001" also appear in D365 ItemGroup "FG-PHARMA", then MATKL "001" ≈ "FG-PHARMA")
4. Present to user for confirmation/correction

### 6.5 Config Merging for Unified Planning

Once entity mappings and inter-company links exist, multiple ERP-sourced SupplyChainConfigs can be merged:

```
┌─────────────────┐   ┌─────────────────┐
│ Config A (SAP)  │   │ Config B (Odoo)  │
│ 20 sites        │   │ 8 sites          │
│ 150 products    │   │ 60 products      │
│ 30 lanes        │   │ 12 lanes         │
│ 5 IC vendors    │   │ 3 IC customers   │
└────────┬────────┘   └────────┬─────────┘
         │                     │
         ▼                     ▼
    ┌──────────────────────────────────┐
    │  Config Merger                    │
    │  1. Resolve IC partners → sites   │  ← Reclassify inter-company
    │  2. Deduplicate sites             │  ← Using erp_entity_mapping
    │  3. Deduplicate products          │
    │  4. Deduplicate external partners │
    │  5. Merge lanes (union + IC→transfer) │
    │  6. Merge BOMs (prefer detail)    │
    │  7. Merge inventory (sum)         │
    │  8. Conflict resolution           │
    └──────────────┬───────────────────┘
                   ▼
    ┌──────────────────────────────────┐
    │  Unified Config                   │
    │  25 sites (3 duplicates resolved) │
    │  180 products (30 deduped)        │
    │  38 lanes (IC lanes = transfers)  │
    └──────────────────────────────────┘
```

**Conflict resolution precedence** (when two ERPs disagree on the same entity):

| Attribute | Precedence Rule |
|-----------|----------------|
| Product description | Longest / most complete |
| Lead time | Prefer ERP that owns the purchasing relationship |
| BOM | Prefer ERP that owns manufacturing |
| Inventory on-hand | Sum (different locations) or latest snapshot (same location) |
| Safety stock / reorder point | Prefer ERP that owns the inventory policy |
| Unit cost | Prefer ERP that owns procurement |
| Vendor attributes | Prefer ERP where POs are actually issued |

---

## 7. Competitive Landscape

| Vendor | Approach | SC-Specific? | Pricing |
|--------|----------|-------------|---------|
| **Bluecrux Axon** | Graph-based digital twin, transaction-driven process mining | Yes | ~$200K-$1M+/yr |
| **Informatica MDM** | Multi-domain MDM, broadest connector library | No — horizontal | ~$150K-$500K+/yr |
| **Stibo Systems** | STEP architecture, product-centric PIM + MDM | Partial | ~$100K-$400K+/yr |
| **Reltio** | Cloud-native graph MDM, real-time entity resolution | No — horizontal | ~$100K-$300K+/yr |
| **Semarchy** | Multi-vector xDM, regulated industries | No — horizontal | ~$80K-$250K+/yr |
| **Syniti** | SAP-focused operational data matching | Partial | ~$100K-$300K+/yr |
| **AWS Entity Resolution** | Rule + ML matching service | No — horizontal | ~$0.25/record |
| **Autonomy (proposed)** | Transaction fuzzy + GTIN/DUNS exact + human confirm | Yes — integrated | Included in platform |

**Autonomy's positioning advantage**: Entity resolution is integrated into the planning pipeline. The cross-ERP mapping feeds directly into unified SupplyChainConfigs, which feed the AI agents. No separate MDM project required.

---

## 8. Implementation Effort

| Component | Effort | Priority |
|-----------|--------|----------|
| `erp_entity_mapping` table + Alembic migration | 1 day | P0 |
| `TradingPartner` inter-company columns + migration | 1 day | P0 |
| `erp_connection_id` FK on SupplyChainConfig | 1 day | P0 |
| Cross-ERP field equivalence registry (AWS SC bridge) | 2 days | P0 |
| Value normalization service (zero-padding, UOM, dates, status) | 3 days | P0 |
| Inter-company detection service (ERP-native flags + Tax ID + DUNS) | 1 week | P0 |
| Lane reclassification (IC partner→site, buy→transfer) | 3 days | P0 |
| GTIN/EAN/DUNS exact matching service (products) | 2 days | P1 |
| Transaction fuzzy matching (PO↔SO, shipment↔receipt) | 1-2 weeks | P1 |
| Description fuzzy matching (TF-IDF + edit distance) | 3 days | P2 |
| Entity resolution review UI (human confirmation) | 1 week | P1 |
| Config merging service | 1 week | P1 |
| Product hierarchy reconciliation | 3 days | P2 |
| **Total** | **~8-9 weeks** | |

---

## 9. Key Takeaway

Bluecrux Axon validates that transaction-driven entity resolution works at enterprise scale. The approach is fundamentally sound because transactions carry more reliable matching signals (dates, quantities, location pairs) than master data descriptions.

The critical enabler — and the piece most implementations skip — is **field-level equivalence** (Section 3). You cannot fuzzy-match a SAP shipment against an Odoo receipt if you don't know that `LIPS.LFIMG` and `stock.move.quantity` both mean "actual shipped quantity." Autonomy's existing per-ERP field mapping services, all resolving through the AWS SC canonical model, provide this Rosetta Stone for free. The AWS SC model is the bridge: SAP field → AWS SC field ← Odoo field, therefore SAP field ≡ Odoo field.

For Autonomy, the implementation is lighter than Axon's full process mining engine because:
1. The per-ERP field mapping services already establish field equivalence via the AWS SC canonical model
2. The staging schemas already contain the transaction data needed for matching
3. `external_identifiers` JSON on Product/TradingPartner already supports multi-ID storage
4. The `source` column on AWS SC entities already tracks provenance

What's needed is: (a) the **value normalization layer** (zero-padding, UOM conversion, date parsing), (b) the **matching logic** (5-tier strategy), and (c) the **cross-reference table** (`erp_entity_mapping`).

---

## References

- Bluecrux Axon Platform: https://www.bluecrux.com/axon/
- Bluecrux Axon 5-Step Approach: https://www.bluecrux.com/axon/5-step-approach/
- Bluecrux — AI & ML in Data Harmonization: https://www.bluecrux.com/blog/the-role-of-ai-ml-in-data-harmonization/
- Bluecrux — Material Flow Analysis with Process Mining: https://www.bluecrux.com/blog/how-to-analyze-material-flows-using-process-mining-techniques/
- Bluecrux — Self-Maintaining Master Data: https://www.bluecrux.com/axon/use-cases/master-data-accuracy/
- Sanofi Case Study: https://www.bluecrux.com/casestudies/sanofi-partners-with-bluecrux-to-optimize-global-operations/
- Wil van der Aalst — Object-Centric Process Mining: https://www.pads.rwth-aachen.de/go/id/sevxe/
- AWS Entity Resolution: https://aws.amazon.com/entity-resolution/
- Syniti Operational Data Matching: https://www.syniti.com/solutions/data-matching/erp-supply-chain-materials-products/
