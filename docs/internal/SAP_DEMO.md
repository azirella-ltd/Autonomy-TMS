# SAP S/4HANA FAA — Demo Scenarios & Autonomy Integration Guide

**Version**: 1.0 | **Date**: 2026-03-08 | **SAP Release**: S/4HANA 2025 (SP00)

This document maps the pre-configured logistics demo scenarios in the SAP S/4HANA Fully-Activated Appliance (FAA) to Autonomy platform capabilities. It serves as the playbook for building side-by-side demonstrations that highlight Autonomy's AI-driven differentiators.

---

## 1. SAP FAA Environment Summary

| Parameter | Value |
|-----------|-------|
| SAP Release | S/4HANA 2025 (SP00) |
| SID | S4H |
| ABAP Instance | 00 |
| HANA DB Instance | 02 |
| Client | 100 (IDES US demo data) |
| Company Code | 1710 (US) |
| Fiori Hostname | `vhcals4hcs.dummy.nodomain` |
| HANA DB Name | HDB, Schema: SAPHANADB |
| SAP Kernel | 916 PL 75 |
| HANA Version | 2.00.087.00 |

### Pre-Connection Checklist

Before connecting Autonomy to the FAA, the following steps must be completed via SAP GUI:

1. **Unlock RFC user** — BPINST is LOCKED by default in the 2025 template. Login as `DDIC` (client 000) or `SAP*` (client 000, Master Password) via SAP GUI. Use tCode `SU01` to unlock the user, or create a dedicated `ZRFC_AUTONOMY` user in client 100 (recommended).
2. **Open MM inventory period** — tCode `MMPV` in client 100 (required for inventory data extraction).
3. **Hosts file mapping** — Add `<ABAP_PUBLIC_IP> vhcals4hcs.dummy.nodomain` to local hosts file for Fiori Launchpad access.
4. **Verify ports** — Ensure AWS Security Group allows inbound on ports 3200 (SAP GUI), 3300 (RFC), 44301 (Fiori HTTPS), 30213/30215 (HANA Studio).

### Autonomy Connection Settings

| Field | Value |
|-------|-------|
| System Type | S/4HANA |
| Connection Method | RFC |
| Application Server | `<ABAP_PUBLIC_IP>` |
| System Number | 00 |
| Client | 100 |
| User | ZRFC_AUTONOMY (or unlocked BPINST) |
| Company Code Filter | 1710 |

### Licensing Timeline

| Period | Status | Action Required |
|--------|--------|-----------------|
| Days 0–30 | Free trial | Hosting fees only (~$3.12/hr on AWS) |
| Days 30–90 | Temporary license | Unlock appliance template in SAP CAL + obtain SAP CAL subscription |
| Day 90+ | License key required | Install S/4HANA, HANA DB, and NetWeaver J2EE license keys via tCodes `/nSLICENSE` and NWA |

---

## 2. FAA Logistics Demo Scenarios

The FAA includes 9 pre-configured logistics demo scenarios with pre-defined users and transactional data. Each scenario below is mapped to the corresponding Autonomy capability.

### 2.1 Sell from Stock with Outbound Delivery Processing

**SAP Process**: Order-to-Cash (OTC) — Sales order creation → availability check → delivery → goods issue → billing.

**Key SAP tCodes**: VA01 (Sales Order), VL01N (Delivery), VL02N (Goods Issue), VF01 (Billing)

**SAP Tables Extracted**:
- `VBAK` / `VBAP` → `outbound_order` / `outbound_order_line`
- `LIKP` / `LIPS` → `shipment` / `shipment_line`
- `MARD` → `inv_level`

**Autonomy Mapping**:
| SAP Step | Autonomy Feature |
|----------|-----------------|
| Manual ATP check (VA01) | **ATP Executor TRM** — AATP with priority consumption, <10ms |
| Delivery creation (VL01N) | **TO Execution TRM** — Automated release, consolidation, expedite |
| Goods issue (VL02N) | **Inventory Management** — Real-time inv_level updates |
| Order tracking | **Order Tracking TRM** — Exception detection and recommended actions |

**Demo Value**: SAP requires manual availability checks per order. Autonomy's AATP handles 100+ decisions/second with priority-based allocation tiers.

---

### 2.2 Warehouse Inbound Processing from Supplier

**SAP Process**: Procure-to-Pay (P2P) — Purchase order → goods receipt → warehouse putaway → invoice verification.

**Key SAP tCodes**: ME21N (PO Creation), MIGO (Goods Receipt), MIRO (Invoice Verification)

**SAP Tables Extracted**:
- `EKKO` / `EKPO` → `inbound_order` / `inbound_order_line`
- `EINA` / `EINE` → `vendor_product` / `vendor_lead_time`
- `EORD` → `sourcing_rules`
- `MARD` → `inv_level`

**Autonomy Mapping**:
| SAP Step | Autonomy Feature |
|----------|-----------------|
| PO creation (ME21N) | **PO Creation TRM** — Optimized timing and quantity |
| Vendor selection | **Sourcing rules** with multi-sourcing priorities |
| Goods receipt (MIGO) | **Inventory Management** — Automatic inv_level update |
| Lead time tracking | **Distribution fitting** — Log-logistic lead time modeling |

**Demo Value**: SAP uses fixed planned delivery times. Autonomy fits actual lead time distributions (log-logistic, Weibull) and uses Monte Carlo DDLT for safety stock calculation.

---

### 2.3 Plan to Produce using Advanced Planning for Capacity Utilization

**SAP Process**: Plan-to-Produce — Demand planning → MPS → capacity leveling → production order → confirmation.

**Key SAP tCodes**: MD61 (Planned Independent Requirements), MD43 (MRP Individual), CM01 (Capacity Leveling), CO01 (Production Order)

**SAP Tables Extracted**:
- `AFKO` / `AFPO` → `production_order` / `production_order_line`
- `STPO` → `product_bom`
- `MARC` → `product` (plant-level data)
- `CRHD` → `resource` (work centers)

**Autonomy Mapping**:
| SAP Step | Autonomy Feature |
|----------|-----------------|
| MPS (MD43) | **Master Production Scheduling** — Strategic production planning with rough-cut capacity |
| Capacity leveling (CM01) | **Capacity Planning** — Resource utilization, bottleneck identification |
| Production order (CO01) | **MO Execution TRM** — Release, sequence, split, expedite, defer |
| Confirmation (CO15) | **CDC Relearning** — Actual outcomes feed back into TRM training |

**Demo Value**: SAP capacity planning is manual leveling. Autonomy uses GraphSAGE for bottleneck detection and MO Execution TRM for automated production scheduling with stochastic yield modeling.

---

### 2.4 Predictive Material & Resource Planning (pMRP)

**SAP Process**: ML-enhanced MRP — Predictive demand → net requirements → planned orders → capacity check.

**Key SAP tCodes**: MD01 (MRP Run), MD04 (Stock/Requirements List), MDBT (MRP Background)

**SAP Tables Extracted**:
- `MARA` / `MARC` → `product`
- `MARD` → `inv_level`
- `STPO` → `product_bom`
- `EKET` → `supply_plan` (PO schedule lines)
- `EORD` → `sourcing_rules`

**Autonomy Mapping**:
| SAP Step | Autonomy Feature |
|----------|-----------------|
| MRP run (MD01) | **Net Requirements Calculator** — Time-phased netting, multi-level BOM explosion |
| Demand forecast | **Demand Processor** — Stochastic forecasting with P10/P50/P90 percentiles |
| Safety stock | **Inventory Target Calculator** — 8 policy types (abs_level, doc_dem, doc_fcst, sl, sl_fitted, conformal, sl_conformal_fitted, econ_optimal) |
| Planned orders | **Supply Plan Generation** — PO/TO/MO requests with sourcing priorities |

**Demo Value**: SAP pMRP produces single-point estimates. Autonomy generates probabilistic supply plans with full uncertainty quantification — "85% chance service level > 95%" vs SAP's deterministic output.

---

### 2.5 Demand-Driven MRP (DDMRP)

**SAP Process**: Buffer-based replenishment — Define buffers → calculate net flow → generate demand-driven planned orders.

**Key SAP tCodes**: MD01 with DDMRP profile, MD04 (Stock/Requirements List)

**SAP Tables Extracted**:
- `MARC` → `product` (MRP profiles, reorder points)
- `MARD` → `inv_level`
- Buffer zone configuration (custom tables)

**Autonomy Mapping**:
| SAP Step | Autonomy Feature |
|----------|-----------------|
| Buffer sizing | **Inventory Buffer TRM** — AI-optimized buffer adjustment |
| Net flow calculation | **`econ_optimal` policy** — Marginal economic return via Monte Carlo DDLT |
| Buffer status monitoring | **Conformal prediction** — Distribution-free guarantee on buffer adequacy |
| Replanning | **CDC Relearning Loop** — Autonomous feedback for continuous improvement |

**Demo Value**: SAP DDMRP uses static buffer zones with manual tuning. Autonomy's Inventory Buffer TRM learns optimal buffer levels from outcomes and automatically reoptimizes via the CDC relearning loop. The `econ_optimal` policy stocks where `stockout_cost × P(demand>k) > holding_cost` — a mathematically rigorous alternative to DDMRP's color-coded zones.

---

### 2.6 Order Management using Advanced Variant Configuration

**SAP Process**: Configure-to-Order — Variant configuration → BOM explosion → routing determination → order creation.

**Key SAP tCodes**: VA01 with variant config, CU41 (Dependency Editor), CS01 (BOM)

**SAP Tables Extracted**:
- `STPO` → `product_bom` (multi-level with variants)
- `MARA` → `product` (configurable materials)
- `VBAK` / `VBAP` → `outbound_order` / `outbound_order_line`

**Autonomy Mapping**:
| SAP Step | Autonomy Feature |
|----------|-----------------|
| BOM explosion | **Multi-level BOM explosion** in Net Requirements Calculator |
| Variant resolution | **product_bom** with scrap rates and transformation ratios |
| Order processing | **ATP Executor TRM** + **MO Execution TRM** |

**Demo Value**: Autonomy handles BOM explosion with stochastic yields and scrap rates — uncertainty propagation through multi-level BOMs that SAP's deterministic explosion cannot provide.

---

### 2.7 Advanced Available-to-Promise / Back Order Processing (aATP, BOP)

**SAP Process**: Advanced ATP — Multi-level availability check → allocation → backorder processing → confirmation.

**Key SAP tCodes**: VA01 (with aATP), /SAPAPO/AC04 (Allocation), /SAPAPO/BOP (Backorder Processing)

**SAP Tables Extracted**:
- `VBAK` / `VBAP` → `outbound_order` / `outbound_order_line`
- `EKET` → `supply_plan` (ATP quantities)
- `MARD` → `inv_level`

**Autonomy Mapping**:
| SAP Step | Autonomy Feature |
|----------|-----------------|
| ATP check | **ATP Executor TRM** — AATP with priority consumption sequence |
| Allocation | **Allocation Service** — Priority × Product × Location from tGNN |
| Backorder processing | **Order Tracking TRM** — Exception detection, recommended actions |
| Confirmation | **Conformal Decision Theory** — P(loss > threshold) on every decision |

**Demo Value**: SAP aATP allocates by customer priority but lacks AI-driven optimization. Autonomy's AATP uses a learned priority consumption sequence: own tier first, then bottom-up from lowest priority, stopping at own tier. The tGNN generates network-wide allocations daily, and CDT provides distribution-free risk bounds on every ATP decision.

**AATP Consumption Logic**:
```
Order at priority P=2: consume [2, 5, 4, 3] (skips priority 1)
Order at priority P=1: consume [1, 5, 4, 3, 2] (all tiers)
```

---

### 2.8 Advanced Intercompany Sales

**SAP Process**: Multi-entity transaction — Intercompany sales order → cross-company delivery → intercompany billing.

**Key SAP tCodes**: VA01 (Intercompany SO), VL01N (Cross-company delivery), VF01 (IC billing)

**SAP Tables Extracted**:
- `VBAK` / `VBAP` → `outbound_order` / `outbound_order_line`
- `T001W` → `site` (multiple plants/companies)
- `LTAK` / `LTAP` → `transfer_order` / `transfer_order_line`

**Autonomy Mapping**:
| SAP Step | Autonomy Feature |
|----------|-----------------|
| Cross-company coordination | **Agentic Authorization Protocol (AAP)** — Layer 3 cross-site authorization |
| Transfer decisions | **Inventory Rebalancing TRM** — Cross-location transfer optimization |
| Multi-site visibility | **Execution tGNN** — Network-wide priority allocations |

**Demo Value**: SAP intercompany sales is a manual, document-driven process. Autonomy's AAP enables autonomous cross-site decisions at machine speed — agents evaluate trade-offs via the Balanced Scorecard and request authorization for actions outside their authority domain. The tGNN provides network-wide visibility that SAP's siloed plant-level view cannot offer.

---

### 2.9 Asset Management (Calibration Processing)

**SAP Process**: Plant Maintenance — Equipment calibration → maintenance order → execution → confirmation.

**Key SAP tCodes**: IW31 (Create PM Order), IW32 (Change PM Order), IE02 (Equipment Master)

**SAP Tables Extracted**:
- `AUFK` (PM module) → `maintenance_order`
- `IHPA` → maintenance partners
- `MHIS` → maintenance history

**Autonomy Mapping**:
| SAP Step | Autonomy Feature |
|----------|-----------------|
| Maintenance scheduling | **Maintenance Scheduling TRM** — Schedule, defer, expedite, outsource |
| Equipment monitoring | **Condition Monitor Service** — Real-time DB condition checks |
| Work order management | **MO Execution TRM** — Release and sequencing |

**Demo Value**: SAP uses time-based preventive maintenance. Autonomy's Maintenance Scheduling TRM uses condition-based AI scheduling that learns optimal maintenance windows from historical outcomes, reducing downtime while avoiding unnecessary preventive actions.

---

## 3. Autonomy Differentiators Not in FAA Demos

These capabilities have no corresponding FAA demo scenario, making them pure Autonomy differentiators:

| Capability | Autonomy Feature | Value |
|-----------|-----------------|-------|
| **Quality Management** | Quality Disposition TRM | AI-driven hold/release/rework/scrap decisions with CDT risk bounds |
| **Subcontracting** | Subcontracting TRM | Make-vs-buy routing optimization with learned cost models |
| **Transportation Optimization** | TO Execution TRM | Consolidation, mode selection, cross-border optimization |
| **Forecast Adjustment** | Forecast Adjustment TRM | Signal-driven adjustments from email, voice, market intelligence |
| **Network Risk Visibility** | S&OP GraphSAGE | Concentration risk, bottleneck detection, resilience scoring |
| **Override Learning** | Bayesian Beta Posteriors | Track human decision quality, feed back into AI training |
| **Probabilistic Planning** | Stochastic Framework | 21 distribution types, Monte Carlo with variance reduction |
| **Decision Intelligence** | Powell SDAM Framework | Full decision lifecycle: model → orchestrate → monitor → govern |

---

## 4. Recommended Demo Sequence

### Demo A: "SAP pMRP vs Autonomy Stochastic Planning"

**Objective**: Show probabilistic supply planning superiority over SAP's deterministic MRP.

**Steps**:
1. Run SAP's pMRP scenario (§2.4) in client 100 — execute `MD01` for plant 1710
2. Extract via Autonomy SAP Data Management: materials (MARA/MARC), BOMs (STPO), inventory (MARD), open POs (EKKO/EKPO), sales orders (VBAK/VBAP), source lists (EORD)
3. Run Autonomy supply plan with stochastic lead times + 8 policy types
4. Compare side-by-side: SAP deterministic safety stock vs Autonomy probabilistic P10/P50/P90

**Key Talking Point**: "SAP says you need 150 units of safety stock. Autonomy says there's an 85% chance your service level exceeds 95% with 120 units — saving $X in holding cost."

---

### Demo B: "SAP DDMRP vs Autonomy Inventory Buffer TRM"

**Objective**: Show AI-optimized buffers that learn from outcomes vs static buffer zones.

**Steps**:
1. Run SAP's DDMRP scenario (§2.5) — configure buffer zones in client 100
2. Extract buffer parameters and inventory data into Autonomy
3. Show Autonomy's `econ_optimal` policy — marginal economic return optimization
4. Show CDC relearning loop: buffer decisions → outcomes → automatic reoptimization

**Key Talking Point**: "SAP DDMRP requires manual buffer tuning every planning cycle. Autonomy's Inventory Buffer TRM learns from every replenishment outcome and reoptimizes automatically."

---

### Demo C: "SAP aATP vs Autonomy AATP"

**Objective**: Show AI-driven ATP at 100x the speed with priority-based allocation.

**Steps**:
1. Run SAP's aATP scenario (§2.7) — process several sales orders with ATP checks
2. Extract order and inventory data into Autonomy
3. Show Autonomy AATP: priority consumption sequence + TRM <10ms decisions
4. Show tGNN-generated allocations (Priority × Product × Location)

**Key Talking Point**: "SAP processes ATP checks one at a time with manual allocation. Autonomy handles 100+ ATP decisions per second with learned priority allocation, and every decision carries a distribution-free risk bound."

---

### Demo D: "SAP Sell from Stock → AI-Automated End-to-End Execution"

**Objective**: Show full autonomous order execution from sales order to delivery.

**Steps**:
1. Run SAP scenario §2.1 end-to-end (order → delivery → goods issue)
2. Extract the complete transaction chain into Autonomy
3. Show Autonomy's TRM Hive handling the full flow: ATP TRM → MO Execution TRM → TO Execution TRM
4. Show the Agentic Authorization Protocol for any cross-site decisions
5. Show override capture and Bayesian posterior tracking

**Key Talking Point**: "What took 4 SAP users and 45 minutes, Autonomy's AI agents handle in under a second — with full explainability and human override tracking."

---

### Demo E: "Network Visibility SAP Can't Provide"

**Objective**: Show AI-driven supply chain risk analysis with no SAP equivalent.

**Steps**:
1. Extract full supply chain topology from SAP: plants (T001W), vendors (LFA1), customers (KNA1), BOMs (STPO), source lists (EORD)
2. Build GraphSAGE network model from real SAP data
3. Show: concentration risk scores, single-source vulnerability, bottleneck detection, resilience scoring
4. Show Site tGNN (Layer 1.5): cross-TRM trade-off detection within each site

**Key Talking Point**: "SAP gives you plant-level visibility. Autonomy gives you network-wide intelligence — which supplier failure would cascade to which customers, and what the AI recommends to mitigate it."

---

## 5. SAP Data Extraction Priority

For the initial demo build, extract SAP tables in this order:

### Phase 1: Master Data (Required for all demos)

| Priority | SAP Table | AWS SC Entity | Records Expected |
|----------|-----------|---------------|-----------------|
| 1 | MARA | product | ~5,000 materials |
| 1 | MARC | product (plant data) | ~15,000 records |
| 1 | T001W | site | ~20 plants |
| 1 | STPO | product_bom | ~10,000 BOM items |
| 1 | EINA / EINE | vendor_product / vendor_lead_time | ~3,000 info records |
| 1 | EORD | sourcing_rules | ~2,000 source list entries |
| 1 | LFA1 | trading_partner (vendors) | ~500 vendors |
| 1 | KNA1 | trading_partner (customers) | ~1,000 customers |

### Phase 2: Transactional Data (Required for demos A-D)

| Priority | SAP Table | AWS SC Entity | Records Expected |
|----------|-----------|---------------|-----------------|
| 2 | MARD | inv_level | ~20,000 stock records |
| 2 | VBAK / VBAP | outbound_order / line | ~10,000 sales orders |
| 2 | EKKO / EKPO | inbound_order / line | ~8,000 purchase orders |
| 2 | AFKO / AFPO | production_order / line | ~5,000 production orders |
| 2 | LIKP / LIPS | shipment / shipment_line | ~7,000 deliveries |

### Phase 3: Historical Data (Required for AI training)

| Priority | SAP Table | Purpose | Records Expected |
|----------|-----------|---------|-----------------|
| 3 | EKBE | Lead time history (GR confirmations) | ~50,000 |
| 3 | MSEG | Inventory movement history | ~100,000 |
| 3 | AFRU | Production confirmation (yield data) | ~20,000 |
| 3 | VBAP (12mo) | Demand history for forecasting | ~30,000 |

---

## 6. CSV Backup Strategy

For connection failure recovery, SAP extracts can be saved as CSVs:

```
imports/SAP/{tenant_name}/
├── master_data/
│   ├── MARA_materials.csv
│   ├── MARC_plant_data.csv
│   ├── T001W_plants.csv
│   ├── STPO_bom.csv
│   ├── EINA_vendor_info.csv
│   ├── EINE_vendor_conditions.csv
│   ├── EORD_source_list.csv
│   ├── LFA1_vendors.csv
│   └── KNA1_customers.csv
├── transactions/
│   ├── MARD_inventory.csv
│   ├── VBAK_sales_orders.csv
│   ├── VBAP_sales_items.csv
│   ├── EKKO_purchase_orders.csv
│   ├── EKPO_purchase_items.csv
│   ├── AFKO_production_headers.csv
│   ├── AFPO_production_items.csv
│   ├── LIKP_delivery_headers.csv
│   └── LIPS_delivery_items.csv
└── history/
    ├── EKBE_po_history.csv
    ├── MSEG_material_documents.csv
    ├── AFRU_confirmations.csv
    └── VBAP_demand_12mo.csv
```

This is not the default extraction behavior — enable via the SAP Data Management connection settings when needed for offline recovery or air-gapped environments.

---

## 7. References

- [SAP S/4HANA FAA Demo Guides — SAP Community](https://community.sap.com/t5/technology-blog-posts-by-sap/sap-s-4hana-fully-activated-appliance-demo-guides/ba-p/13389412)
- [SAP S/4HANA FAA Getting Started Guide v21](SAP/Documentation/SAP_Getting_Started_Guide_v21.pdf) (local)
- [SAP S/4HANA 2025 FAA Known Issues](https://community.sap.com/t5/technology-blog-posts-by-sap/sap-s-4hana-2025-fully-activated-appliance-known-issues/ba-p/14260301)
- [SAP S/4HANA FAA Demo Guides & System Access — LinkedIn](https://www.linkedin.com/pulse/sap-s4hana-fully-activated-appliance-demo-guides-system-mh)
- [SAP DDMRP Functionality](https://blogs.sap.com/2019/02/17/s4hana-demand-driven-mrp-ddmrp-functionality/)
- [Demo Script: Transportation Mgmt Basic Outbound (FPS03)](https://www.sap.com/documents/2025/05/6e7a09ef-037f-0010-bca6-c68f7e60039b.html)
- [SAP Integration Guide](docs/progress/SAP_INTEGRATION_GUIDE.md) (internal)
- [AWS SC Implementation Status](docs/progress/AWS_SC_IMPLEMENTATION_STATUS.md) (internal)
