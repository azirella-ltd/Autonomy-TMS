# SAP S/4HANA FAA — Demo Scenarios & Autonomy Integration Guide

**Version**: 2.0 | **Date**: 2026-03-18 | **SAP Release**: S/4HANA 2025 (SP00)

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

### SAP CAL Appliance Setup

The FAA is provisioned via SAP Cloud Appliance Library (CAL) at [cal.sap.com](https://cal.sap.com). Our appliance is named **"Autonomy"**.

**Appliance Template**: SAP S/4HANA 2025, Fully-Activated Appliance (SP00, Update 25)

#### Virtual Machines

| VM | Size | Purpose |
|----|------|---------|
| SAP S/4HANA 2025 & SAP HANA DB 2.0 | r6i.8xlarge (32 cores, 256GB) | ABAP + HANA database |
| SAP NetWeaver 7.50 SP32 AS JAVA | r6i.xlarge (4 cores, 32GB) | Java stack, Adobe Document Services |
| Windows Remote Desktop | m6i.xlarge (4 cores, 16GB) | SAP GUI access, admin tasks |

**Running cost**: ~$3.12/hr (~$75/day) when all 3 VMs are active. Suspend when not in use.

#### CAL Configuration Checklist

After creating the appliance, configure these settings before first use:

| Setting | Location | Required Value | Why |
|---------|----------|---------------|-----|
| **Public Static IP** | Info tab | Enabled (checkbox) | Prevents external IPs from changing on every restart |
| **Termination Protection** | Info tab | Enabled (checkbox) | Prevents accidental deletion |
| **Schedule** | Schedule tab | "Manually activate and suspend" | Prevents unexpected suspension; control costs manually |
| **IP Range (Access Points)** | Virtual Machines tab | Your public IP with `/32` mask | Restricts access to your machine only |
| **Backups** | Backups tab | Create initial backup | Protects against configuration loss |

#### Access Points (Ports)

All ports are on the **SAP S/4HANA 2025 & SAP HANA DB 2.0** VM unless noted:

| Port | Service | Purpose |
|------|---------|---------|
| 3389 | RDP | Windows Remote Desktop VM access |
| 3200 | SAP GUI | ABAP client access (SAPGUI protocol) |
| 3300 | RFC | Remote Function Call (used by Autonomy connection) |
| 8443 | SAP Cloud Connector | Cloud integration |
| 44300 | Fiori HTTP | Fiori Launchpad (HTTP) |
| 44301 | Fiori HTTPS | Fiori Launchpad (HTTPS) |
| 50000 | HTTP Admin | NetWeaver HTTP administration |
| 30213 | HANA Studio | HANA database administration |
| 30215 | HANA indexserver | HANA SQL access |
| 22 | SSH | Shell access to S/4HANA VM |

**Security**: Set the IP Range for all access points to `<YOUR_PUBLIC_IP>/32`. Determine your public IP with `curl ifconfig.me`. If your ISP uses dual-stack (IPv4 + IPv6), you may need to add both your IPv4 (`x.x.x.x/32`) and IPv6 (`xxxx:xxxx:.../128`) addresses — AWS security groups must allow whichever protocol your traffic arrives on. If connectivity fails after restricting, temporarily use "Clear Restrictions" to reset to `0.0.0.0/0` and troubleshoot.

#### Connection Details

External IPs are assigned by AWS. With **Public Static IP** enabled (confirmed), these persist across restarts:

| VM | Internal IP | External IP | Primary Access |
|----|-------------|-------------|----------------|
| SAP S/4HANA 2025 & SAP HANA DB 2.0 | 10.0.8.104 | `63.182.191.72` | RFC 3300, Fiori 44301, HANA 30215, SAP GUI 3200 |
| SAP NetWeaver 7.50 AS JAVA | 10.0.3.227 | `35.157.182.78` | HTTP 50000 |
| Windows Remote Desktop | 10.0.15.197 | `3.124.111.17` | RDP 3389 (direct, no SSH tunnel) |

**Region**: eu-central-1 (Frankfurt) | **Account**: AWS Autonomy | **Termination Protection**: Enabled

**Note**: Internal IPs are stable within the VPC. From the Windows RDP VM, connect to SAP GUI using the internal IP (10.0.8.104) rather than the external IP.

#### Licensing

| Period | Status | Action Required |
|--------|--------|-----------------|
| Days 0–30 | Free trial | Hosting fees only |
| Days 30–90 | Temporary license | Unlock appliance template in SAP CAL |
| Day 90+ | License key required | Install keys via `/nSLICENSE` (ABAP) and NWA (Java) |

License expiry is shown on the License Status tab in CAL. Plan demo timelines accordingly.

#### Suspend / Activate

- **Suspend**: Appliances list → three-dot menu (**...**) → Suspend. Stops all VMs, preserves data. Storage fees only (~$5-10/day).
- **Activate**: Appliances list → click "Activate". Takes 10-15 minutes for all VMs to start and SAP services to initialize.
- **Schedule**: Use "Suspend on an exact date" as a safety net to avoid runaway costs if you forget to suspend manually. Set to a date before license expiry.

#### RDP Access to Windows VM

RDP is required for SAP GUI access (pre-connection steps, demo execution, user management).

**Prerequisites**:
- RDP client installed (Linux: Remmina or xfreerdp; macOS: Microsoft Remote Desktop; Windows: built-in)
- Access Points IP Range allows your public IP

**Connection** (current instance):

| Field | Value |
|-------|-------|
| Protocol | RDP |
| Server | `3.124.111.17` |
| Port | 3389 |
| Username | `Administrator` |
| Password | Master Password (set during CAL appliance creation) |
| SSH Tunnel | **NOT needed** — RDP port is directly accessible |

**Local files** (in `~/Downloads/`):
- `Autonomy.pem` — SSH key (encrypted, for SSH-based access if needed)
- `Autonomy.sap` — SAP GUI connection file (points to 63.182.191.72, SID S4H, instance 00, client 100)

**Linux (Remmina)** — direct RDP (no SSH tunnel):
1. Open Remmina → open saved profile "SAP RDP" or create new
2. **Basic tab**: Protocol: RDP, Server: `3.124.111.17`, Username: `Administrator`, Password: master password
3. **SSH Tunnel tab**: Ensure "Enable SSH tunnel" is **UNCHECKED** (port 22 is not open on the Windows VM; RDP 3389 is directly accessible)
4. Click "Save and Connect"

**Alternative (xfreerdp)**:
```bash
xfreerdp3 /v:3.124.111.17 /u:Administrator /port:3389 /size:1920x1080
```

**Troubleshooting RDP**:
- **"Could not resolve hostname to IPv6"**: Your network may route via IPv6 but the SAP security group only allows IPv4. Add your IPv6 address to the Access Points IP Range, or use xfreerdp with explicit IPv4.
- **Connection timeout**: Check that the appliance is Active in CAL (not Suspended). Verify Access Points IP Range includes your current public IP.
- **After reactivation**: If Public Static IP was enabled (it is), external IPs persist. If not, check the Info tab for new IPs.
- **SSH tunnel fails**: Don't use SSH tunnel — port 22 is not open on the Windows VM. Connect directly on port 3389.

**Once connected**: SAP GUI is pre-installed on the Windows desktop with a connection pre-configured to the S/4HANA system (internal IP 10.0.8.104, instance 00).

### Pre-Connection Checklist

Before connecting Autonomy to the FAA, the following steps must be completed via SAP GUI.
For detailed user permissions by connection type (RFC, OData, HANA DB, CSV), see [SAP Integration Guide — User Permissions](../external/SAP_INTEGRATION_GUIDE.md#sap-user-permissions-by-connection-type).

1. **Unlock RFC user** — BPINST is LOCKED by default in the 2025 template. Login as `DDIC` (client 000) or `SAP*` (client 000, Master Password) via SAP GUI. Use tCode `SU01` to unlock the user, or create a dedicated `ZRFC_AUTONOMY` user in client 100 (recommended).
2. **Open MM inventory period** — tCode `MMPV` in client 100 (required for inventory data extraction).
3. **Hosts file mapping** — Add `<ABAP_PUBLIC_IP> vhcals4hcs.dummy.nodomain` to local hosts file for Fiori Launchpad access.
4. **Verify ports** — Ensure AWS Security Group allows inbound on ports 3200 (SAP GUI), 3300 (RFC), 44301 (Fiori HTTPS), 30213/30215 (HANA Studio).

### Autonomy Connection Settings

| Field | Value |
|-------|-------|
| System Type | S/4HANA |
| Connection Method | RFC |
| Application Server | `63.182.191.72` |
| System Number | 00 |
| Client | 100 |
| User | ZRFC_AUTONOMY (or unlocked BPINST) |
| Company Code Filter | 1710 |

#### Autonomy Integration Quick Reference (Current Instance)

| Connection | Host | Port | User | Password | Schema/SID |
|-----------|------|------|------|----------|-----------|
| **HANA DB** (extraction) | `63.182.191.72` | 30215 | `SAPHANADB` | `Wedding$19890617#` | Schema: `SAPHANADB` |
| **RFC** (real-time) | `63.182.191.72` | 3300 | `ZRFC_AUTONO` | `Autonomy@2026` (reset 2026-03-22) | SID: S4H, Instance: 00, Client: 100 |
| **OData** (REST) | `63.182.191.72` | 44301 (HTTPS) | N/A — ZRFC_AUTONO is User Type B (System), cannot auth via HTTP | — |
| **SAP GUI** (via RDP) | `10.0.8.104` (internal) | 3200 | `DDIC` / client 000 | `Wedding$19890617#` | SID: S4H, Instance: 00 |
| **Windows RDP** | `3.124.111.17` | 3389 | `Administrator` | `Wedding$19890617#` | No SSH tunnel needed |

**Master Password**: `Wedding$19890617#` (set during CAL appliance creation; used for DDIC, Administrator, SAPHANADB, SYSTEM HANA users)

**ABAP Users** (Client 100):
- `ZRFC_AUTONO` — Autonomy RFC User, Type B (System), password `Autonomy@2026`. Status: Saved (not locked). Has `ZRFC_AUTONOMY` role with RFC table read + BAPI access.
- `BPINST` — Technical user, password `Welcome1`. May need unlocking after fresh activation via SU01.

**Demo Users** (Client 100, Password: `Welcome1`):
`S4H_SD_DEM` (Sales), `S4H_MM_DEM` (Purchasing), `S4H_PP_DEM` (Production), `S4H_EWM_DEM` (Warehouse), `S4H_PM_DEM` (Maintenance)

**HANA DB Notes** (discovered 2026-03-22):
- `SAPHANADB` user has SELECT access to all tables but **cannot CREATE USER or ALTER USER** (insufficient privilege)
- `SYSTEM` user password is NOT the same as the master password — authentication fails with the master password
- `AUTONOMY_EXTRACT` user does not exist on this instance (cannot be created without SYSTEM access)
- **Workaround**: Extract directly as `SAPHANADB` — works for all SELECT operations
- DBA Cockpit SQL Editor (tCode DBACOCKPIT → Diagnostics → SQL Editor) runs as SAPHANADB — cannot CREATE USER

**S/4HANA 2025 Data Model Notes** (discovered 2026-03-22):
- Many ECC column names have been removed/renamed in S/4HANA 2025 (BUKRS not on T001W, STLNR not on MARC, etc.)
- The extraction script uses **auto-discovered columns** (`SELECT COLUMN_NAME FROM TABLE_COLUMNS`) to avoid hardcoded field lists
- MARC has **309 columns** in S/4HANA 2025 (vs ~30 in the hardcoded list)
- All 20 MRP planning fields confirmed present: DISMM, DISLS, VRMOD, VINT1, VINT2, FXHOR, STRGR, MINBE, EISBE, MABST, LOSGR, BSTMI, BSTMA, BSTRF, SHZET, RDPRF, AUSSS, DZEIT, BESKZ, PLIFZ

**HANA DB extraction command** (from Autonomy host):
```bash
cd /home/trevor/Documents/Autonomy/backend
# Uses auto-column-discovery (inline script) — handles S/4HANA 2025 schema changes
python3 scripts/extract_sap_hana.py \
    --host 63.182.191.72 --port 30215 \
    --user SAPHANADB --password 'Wedding$19890617#' \
    --company-code 1710 \
    --output-dir ../imports/sap_faa_extract_20260322
```

**Last extraction**: 2026-03-22 — 191,584 rows across 49 tables. Key tables: MARC (669 rows, 309 cols), MARA (2,770), STKO (284), STPO (1,400), AFKO (1,138), EKPO (10,813), VBAP (8,609).

**First-time setup on fresh activation**:
1. RDP to `3.124.111.17` → login as `Administrator` / master password
2. Open SAP GUI → client 000 → login as `DDIC` / master password
3. tCode `SU01` → unlock `BPINST` user (if needed)
4. tCode `SU01` → reset `ZRFC_AUTONO` password if needed
5. HANA user creation: use DBA Cockpit SQL Editor (DBACOCKPIT → Diagnostics → SQL Editor) — but note SAPHANADB user cannot CREATE USER. Alternative: direct extraction as SAPHANADB works fine.
6. (Optional) To create AUTONOMY_EXTRACT: need SYSTEM user access — password unknown on current instance. Reset via HANA recovery or SAP Note 1600929.
   ```sql
   CREATE USER AUTONOMY_EXTRACT PASSWORD "Autonomy@2026" NO FORCE_FIRST_PASSWORD_CHANGE;
   GRANT SELECT ON SCHEMA SAPHANADB TO AUTONOMY_EXTRACT;
   GRANT CATALOG READ TO AUTONOMY_EXTRACT;
   ```

#### Running MRP Remotely (Baseline Plan)

**Why**: The digital twin mirrors SAP's MRP heuristics. To validate the mirror, we need SAP's actual MRP output (planned orders) as ground truth. The comparison: "Does Autonomy's `compute_replenishment()` produce the same planned orders as SAP's MD01 for the same material-plant with the same MARC parameters?"

**Remote execution options** (investigated 2026-03-22):

| Method | Status | Notes |
|--------|--------|-------|
| **RFC via pyrfc** | ❌ Not available | `pyrfc` requires SAP NW RFC SDK (C library) — not installed locally or in Docker. Function modules: `BAPI_MATERIAL_PLANNING`, `MD_RUN_MRP`, `BAPI_REQUIREMENTS_GETDETAIL` |
| **OData** | ❌ Cannot auth | `ZRFC_AUTONO` is User Type B (System) — cannot authenticate via HTTP. OData services require Dialog or Communication type users. |
| **HANA SQL direct** | ⚠️ Read-only | Can READ planned orders (PLAF), MRP lists (MDKP/MDTB or PPH_*), stock/requirements — but **cannot EXECUTE MRP** (that requires ABAP runtime) |
| **SAP GUI via RDP** | ✅ Works | Only option for running MRP transactions (MD01/MD02). Must be done interactively. |

**To install pyrfc** (future — enables remote MRP execution):
1. Download SAP NW RFC SDK from [SAP Support Launchpad](https://launchpad.support.sap.com/#/softwarecenter) (requires S-user)
2. Install: `pip install pyrfc` + set `SAPNWRFC_HOME` to SDK lib path
3. Then `Connection(ashost='63.182.191.72', sysnr='00', client='100', user='ZRFC_AUTONO', passwd='Autonomy@2026')`
4. Call: `conn.call('BAPI_MATERIAL_PLANNING', PLANT='1710', MATERIAL='AVC_RBT_BUNDLE')`

**Manual MRP via SAP GUI** (via RDP):

1. **Run MRP** — tCode `MD01` (total) or `MD02` (single material):
   - Plant: `1710`, Processing: `NETCH`, Create PR: `1`, MRP List: `1`
   - For single material: `MD02` → Material `AVC_RBT_BUNDLE` → Plant `1710`

2. **Check results** — tCode `MD04` (stock/requirements list):
   - Material + Plant → shows planned orders, safety stock, exception messages
   - This is the **ground truth** for mirror validation

3. **Extract results** — after MRP run, extract PLAF (planned orders) via HANA:
   ```sql
   SELECT MATNR, PLWRK, PLART, GSMNG, PSTTR, PEDTR, VEESSION
   FROM SAPHANADB.PLAF
   WHERE MANDT='100' AND PLWRK='1710'
   ORDER BY MATNR, PSTTR
   ```

**What we do with the results**:
1. Extract PLAF (planned orders) to CSV after MRP run
2. For each material: compare SAP's planned order qty/date against `heuristic_library.compute_replenishment()` output with the same MARC parameters
3. Discrepancies indicate mirror bugs — fix until output matches
4. This becomes a **regression test** per DIGITAL_TWIN.md §8A.11

**Existing MRP baseline** (discovered 2026-03-22):
- **313 planned orders** already exist in PLAF from prior IDES demo MRP runs
- Extracted to `imports/sap_faa_extract_20260322/PLAF.csv` (139 columns)
- All top materials use DISMM=PD, DISLS=EX, LOSGR=100, STRGR=40 or 70
- Date range: 2020–2025 (historical IDES demo data)
- Top materials: SG21 (44 orders, 4,651 units), FG1_CP (30 orders), SG224 (28 orders)

**Running a fresh MRP (via SAP GUI on RDP)**:

1. **Total MRP** — tCode `/nMD01`:
   | Field | Value |
   |-------|-------|
   | Plant | `1710` |
   | MRP | `NETCH` (net change in total horizon) |
   | Create purchase req | `1` |
   | Schedule lines | blank |
   | MRP list | `1` (create) |
   | Planning mode | `1` (adapt existing) |
   | Scheduling | `1` (basic dates) |

   Press F8 to execute. Takes 1-5 minutes for plant 1710.

2. **Single-material MRP** — tCode `/nMD02`:
   | Field | Value |
   |-------|-------|
   | Material | e.g., `SG21` |
   | Plant | `1710` |
   | Processing Key | `NETCH` |

   Press F8. Instant for single material.

3. **Check results** — tCode `/nMD04`:
   - Enter material + plant → shows stock/requirements list
   - Shows: planned orders, firmed orders, safety stock, exception messages
   - This is the **ground truth** for heuristic mirror validation

4. **Extract results via HANA** (after MRP run):
   ```bash
   python3 << 'PYEOF'
   import sys; sys.path.insert(0, 'backend')
   from hdbcli import dbapi
   conn = dbapi.connect(address='63.182.191.72', port=30215,
       user='SAPHANADB', password='Wedding$19890617#',
       encrypt=True, sslValidateCertificate=False)
   cursor = conn.cursor()
   cursor.execute("""
       SELECT MATNR, PLWRK, GSMNG, PSTTR, PEDTR, BESKZ
       FROM SAPHANADB.PLAF
       WHERE MANDT='100' AND PLWRK='1710'
       ORDER BY MATNR, PSTTR
   """)
   for r in cursor.fetchall():
       print(f"{r[0]:30s} plant={r[1]} qty={r[2]:>8} start={r[3]} end={r[4]} proc={r[5]}")
   conn.close()
   PYEOF
   ```

**Key materials for validation** (from extraction — DISMM=PD, representative of 161/178 products):
- `SG21` — manufactured (BESKZ=E), STRGR=40, LOSGR=100 — **44 existing planned orders** (highest count)
- `FG1_CP` — manufactured (BESKZ=E), STRGR=40, LOSGR=100 — 30 planned orders
- `AVC_RBT_BUNDLE` — manufactured (BESKZ=E), STRGR=25, LOSGR=100, DZEIT=2d — 0 planned orders (no demand)
- `FG3_CP` — mixed (BESKZ=X), STRGR=70, LOSGR=1 — 10 planned orders

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
| Cross-company coordination | **Agentic Authorization Protocol (AAP)** — AAP Protocol cross-site authorization |
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
4. Show Site tGNN (Layer 2): cross-TRM trade-off detection within each site

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

## 7. IDES 1710 Entity Reference

> **Active Config**: ID 82 (SAP IDES 1710 — Plant 1 US, v3), Tenant 20
> **CSV Location**: `imports/SAP/IDES_1710/` (50 CSV files)

### SAP Official Demo Script Values

These are the **exact field values** used in SAP's published demo scripts (BD9, Plan to Produce, etc.). Use these when demoing to SAP people — they will recognize these as the standard FAA demo data.

| Demo | tCode | Customer | Material | Plant | Sales Org |
|------|-------|----------|----------|-------|-----------|
| **Sell from Stock (BD9)** | VA01→VL01N→VF01 | `17100001` (Domestic US Customer 1) | `TG11` (Trading Good 11) | `1710` | `1710/10/00` |
| **Sell from Stock (alt)** | VA01 | `17100003` (Domestic Customer US 3) | `TG12` (Trading Good 12) | `1710` | `1710/10/00` |
| **Plan to Produce** | MD04→CO01→CO11N | — | `FG126` (Finished Good 126, MTS-DI) | `1710` | — |
| **Variant Configuration** | VA01→CU41→CS01 | — | `AVC_RBT_ROBOT` (Robot Base Unit) | `1710` | `1710/10/00` |
| **EWM Warehouse** | /SCWM/* | `EWM17-CU01` | `EWMS4-01`, `EWMS4-02` | `1710` | — |
| **Intercompany** | VA01 | `17100011` | TG11 | `1710` | `1710/10/00` |

**Demo Users** (Client 100, Password: `Welcome1`): `S4H_SD_DEM` (Sales), `S4H_MM_DEM` (Purchasing), `S4H_PP_DEM` (Production), `S4H_EWM_DEM` (Warehouse), `S4H_PM_DEM` (Maintenance/Quality)

### Extended SC Planning Data (MZ Bikes)

The MZ Motorcycle Zone product line provides richer supply chain data for planning demos — BOMs, multiple customers, purchase orders, production history. Use this data for Autonomy-specific demos (stochastic planning, AI agents, scenario events).

### Plants/Sites

| SAP Code | Name | DB Site ID | master_type |
|----------|------|-----------|-------------|
| 1710 | Plant 1 US (Palo Alto, CA) | 1352 | MANUFACTURER |
| 1711 | Plant 1 US (Storage) | 1353 | INVENTORY |
| 1712 | Plant 2 US (Storage) | 1354 | INVENTORY |
| 1720 | Plant 2 US (Sacramento, CA) | 1355 | INVENTORY |

**Storage Locations (Plant 1710)**: 171A (Std. storage 1), 171B (Std. storage 2), 171C (Raw Materials), 171D (EWM Rec. on Dock), 171E (KANBAN)

### Finished Goods — Motorcycle Zone (MZ)

Three product families, 9 finished goods manufactured at Plant 1710:

| Product ID | Description | Family |
|-----------|-------------|--------|
| MZ-FG-C900 | C900 BIKE | City |
| MZ-FG-C950 | C950 BIKE | City |
| MZ-FG-C990 | C990 Bike | City |
| MZ-FG-M500 | M500 BIKE | Mountain |
| MZ-FG-M525 | M525 BIKE | Mountain |
| MZ-FG-M550 | M550 BIKE | Mountain |
| MZ-FG-R100 | R100 BIKE | Road |
| MZ-FG-R200 | R200 Bike | Road |
| MZ-FG-R300 | R300 Bike | Road |

**Trading Goods**: MZ-TG-Y120 (Y120 Bike), MZ-TG-Y200 (Y200 Bike), MZ-TG-Y240 (Y240 Bike) — purchased, not manufactured.

**Raw Materials**: Each bike has 7-10 components (Frame, Handle Bars, Seat, Wheels, Forks, Brakes, Drive Train, plus Derailleur Gears, Pedal Kit, Shock Kit for M/R series). Pattern: `MZ-RM-{bike}-{seq}` (e.g., MZ-RM-C900-01 = Frame 900). Total: 81 raw materials.

### Other Product Lines

| Product ID | Description | Category |
|-----------|-------------|----------|
| AVC_RBT_BUNDLE | Robot Bundle | Robotics |
| AVC_RBT_ROBOT | Robot Base Unit | Robotics |
| AVC_RBT_ROBOT2 | Robot Multi-Level | Robotics |
| CM-FL-V00 | Forklift | Capital Equipment |
| CEMENT-100 | CEMENT-100 | Process |

### Key Customers — Named Bike Dealers (USCU_*)

**Large Accounts (L-prefix)**:

| DB Name | Company | City, State | DB ID |
|---------|---------|-------------|-------|
| CUST-USCU_L01 | Skymart Corp | New York, NY | 1362 |
| CUST-USCU_L02 | Toys4U | Wilmington, DE | 1361 |
| CUST-USCU_L03 | Viadox | Baltimore, MD | 1360 |
| CUST-USCU_L04 | Quotex | Raleigh, NC | 1367 |
| CUST-USCU_L05 | Bluestar Corp | Charleston, SC | 1374 |
| CUST-USCU_L06 | Dexon | Nashville, TN | 1370 |
| CUST-USCU_L07 | Interlude Inc | Miami, FL | 1368 |
| CUST-USCU_L08 | Veracity | Atlanta, GA | 1373 |
| CUST-USCU_L09 | **Bigmart** | Detroit, MI | 1357 |
| CUST-USCU_L10 | CostClub | Cleveland, OH | 1358 |

**Small Accounts (S-prefix)**:

| DB Name | Company | City, State | DB ID |
|---------|---------|-------------|-------|
| CUST-USCU_S01 | Performance Bikes | Pittsburgh, PA | 1371 |
| CUST-USCU_S02 | Custom Sports | Boston, MA | 1369 |
| CUST-USCU_S03 | Eastside Bikes | Greensburg, PA | 1377 |
| CUST-USCU_S04 | Fit Cycles | Portland, ME | 1372 |
| CUST-USCU_S05 | Greater Hartford Area | Hartford, CT | 1379 |
| CUST-USCU_S06 | Hub & Spokes Inc | Manhattan, NY | 1384 |
| CUST-USCU_S07 | Westend Cycles | Raleigh, NC | 1380 |
| CUST-USCU_S08 | Velocity Cycles | Charleston, SC | 1382 |
| CUST-USCU_S09 | Greenhigh Bikes | Nashville, TN | 1385 |
| CUST-USCU_S10 | Turbo Bikes | Miami, FL | 1376 |
| CUST-USCU_S11 | Bike World | Atlanta, GA | 1381 |
| CUST-USCU_S12 | Century Cycles | Richmond, VA | 1383 |
| CUST-USCU_S13 | Rolling Bike Shop | Montgomery, AL | 1378 |
| CUST-USCU_S14 | Cityscape Cycles | Chicago, IL | 1366 |
| CUST-USCU_S15 | Northside Bikes | Des Moines, IA | 1363 |
| CUST-USCU_S16 | Gogo Bikes | Milwaukee, WI | 1364 |
| CUST-USCU_S17 | Bikepros | Minneapolis, MN | 1365 |

**Generic Customers** (for non-bike demos):

| DB Name | Description | DB ID |
|---------|-------------|-------|
| CUST-0017100001 | Domestic US Customer 1 | 1356 |
| CUST-0017100006 | Domestic Customer US 6 (Returns) | 1387 |
| CUST-0017100051 | Foreign Customer 51 (CA) | 1404 |

### Key Vendors/Suppliers

| DB Name | Description | DB ID |
|---------|-------------|-------|
| VEND-USSU-VSF01 | EV Parts Inc. | 1417 |
| VEND-USSU-VSF02 | WaveCrest Labs | 1421 |
| VEND-0017300001 | Domestic US Supplier 1 | 1422 |
| VEND-0017300002 | Domestic US Supplier 2 | 1425 |
| VEND-0017300003 | Domestic US Supplier 3 (with ERS) | 1428 |
| VEND-0017300006 | Domestic US Supplier 6 (Returns) | 1424 |
| VEND-0017300007 | Domestic US Subcontractor A | 1426 |

### Data Population Status

| Entity | DB Count | CSV Available? | Status |
|--------|----------|---------------|--------|
| Products | 178 | MARA/MAKT ✅ | Present |
| Sites | 89 (4 internal, 59 customers, 26 vendors) | T001W/KNA1/LFA1 ✅ | Present |
| Transportation lanes | 88 | EORD ✅ | Present |
| Inventory levels | 178 (1 site only) | MARD ✅ (1,035 records) | Partial — only 1 site loaded |
| **BOMs** | **0** | STPO ✅, STKO ✅, **MAST ❌** | **BLOCKED** — builder bug (parent/component swap) + MAST not extracted |
| **Forecasts** | **0** | PBIM/PBED ✅ (no MZ data) | **MISSING** — PIR has no MZ bike entries; need VBAP-based demand history |
| **Outbound orders** | **0** | VBAK ✅ (8,148), VBAP ✅ | **NOT INGESTED** — builder method exists but buggy |
| **Inbound orders** | **0** | EKKO ✅ (2,223), EKPO ✅ | **NOT INGESTED** — builder uses raw SQL fallback |
| **Production orders** | **0** | AFKO ✅ (1,123), AFPO ✅ | **NOT INGESTED** — builder method exists, not fully wired |

### History Data for AI Training

| Table | Purpose | `SAP/IDES_1710/` | `sap_faa_extract/` | Records |
|-------|---------|-------------------|--------------------|---------|
| **EKBE** | PO history (goods receipts) | ❌ | ✅ | 17,975 (988 match MZ POs) |
| **AFRU** | Production confirmations | ❌ | ✅ | 1,656 |
| **KNVV** | Customer sales area data | ❌ | ✅ | 1,313 |
| **AFVC** | Production operations | ✅ | ✅ | 2,478 |
| **QALS** | Quality inspection lots | ✅ | ✅ | 250 |
| **MSEG** | Goods movements | ❌ (header only) | ❌ (header only) | 0 — **re-extract needed** |
| **KONV** | Pricing conditions | — | ❌ (header only) | 0 — **re-extract needed** |

> **NOTE**: `sap_faa_extract/` and `sap_faa_full_extract/` contain richer data than `SAP/IDES_1710/`. The builder currently reads from `SAP/IDES_1710/` only. Need to consolidate directories or update builder path.

### Truly Missing — Must Extract from FAA

| Table | Purpose | Impact |
|-------|---------|--------|
| **MAST** | Material BOM Assignment (MATNR→STLNR) | Cannot populate `product_bom` — BOM explosion blocked |
| **MSEG** | Goods movement items | Re-extract with corrected query (current extraction returned 0 rows) |
| **KONV** | Pricing condition values | Re-extract with corrected query |

---

## 8. Scenario Event Catalog (24 Types)

These can be triggered via Azirella natural language or the Scenario Events UI.

> **For SAP audiences**: Use the SAP official materials (TG11, FG126, customer 17100001) for standard demo flows.
> **For SC planning/AI demos**: Use MZ bikes (C900, M500, R200) and named customers (Bigmart, Skymart) for richer scenarios.

### Demand Events

1. **drop_in_order** — SAP: "Customer 17100001 places a rush order for 100 TG11, delivery in 2 weeks" / MZ: "Bigmart places a rush order for 500 C900 bikes, delivery in 2 weeks"
2. **demand_spike** — "20% demand increase on M-series bikes for 8 weeks (summer season)"
3. **order_cancellation** — "CostClub cancels their standing order for R200 bikes"
4. **forecast_revision** — "Reduce R-series forecast by 15% for next quarter"
5. **customer_return** — "Veracity returns 200 C950 bikes — quality defect in Brakes-950"
6. **product_phase_out** — "Phase out Y120 bike, replace with Y240 over 8 weeks"
7. **new_product_introduction** — "Introduce E-Bike (MZ-FG-E100) at Plant 1710, 100/week, launch in 6 weeks"

### Supply Events

8. **supplier_delay** — "EV Parts Inc. delayed by 14 days on all open POs"
9. **supplier_loss** — "WaveCrest Labs declares bankruptcy — all supply lost"
10. **quality_hold** — "Quality hold on 500 units of Frame 900 at Plant 1710"
11. **component_shortage** — "1000 units of Wheels-900 damaged in warehouse — write off"
12. **supplier_price_change** — "EV Parts Inc. raises prices by 12% on all components"
13. **product_recall** — "Mandatory recall: 300 C990 bikes — brake defect"

### Capacity Events

14. **capacity_loss** — "Plant 1710 loses 40% production capacity for 3 weeks"
15. **machine_breakdown** — "Assembly Line A at Plant 1710 breaks down — 5 days repair"
16. **yield_loss** — "C900 assembly scrap rate increases 15% for 4 weeks"
17. **labor_shortage** — "Plant 1710 loses 30% labor — flu outbreak on day shift, 2 weeks"
18. **engineering_change** — "Substitute Brakes-900 with BKC-990 Brakes on C900 bike"

### Logistics Events

19. **shipment_delay** — "Shipment from Plant 1710 to Plant 1720 delayed by 7 days"
20. **lane_disruption** — "Lane from Supplier 1 to Plant 1710 blocked for 3 weeks"
21. **warehouse_capacity_constraint** — "Plant 1711 warehouse at 95% utilization, expected 4 weeks"

### Macro Events

22. **tariff_change** — "15% tariff increase on imports from Domestic US Supplier 2"
23. **currency_fluctuation** — "EUR/USD weakens by 8%"
24. **regulatory_change** — "CPSC safety regulation: additional brake testing on all bike models, 90-day deadline"

---

## 9. SAP Change Simulator — Extract Once, Simulate Ongoing

**Purpose**: Extract all data from SAP in a single session (~1-2 hours, ~$3-6), then shut down the FAA to save ~$75/day. A lightweight simulator generates realistic change events that trigger Autonomy's existing CDC pipeline — no SAP needed.

### 8.1 Phase 1: Full SAP Extraction (SAP Running)

1. Connect Autonomy → SAP via RFC (see §1)
2. Extract all 3 phases from §5 (master data → transactions → history)
3. Save CSVs to `imports/SAP/{tenant_name}/` as backup (see §6)
4. Load everything into Autonomy's DB via SAP Data Management ingestion
5. **Stop SAP instances** via SAP CAL console

### 8.2 Phase 2: SAP Change Simulator (SAP Offline)

Three layers generate realistic delta events from the extracted baseline:

**Layer 1 — Demand Generator** (simulates customer order flow)
- Uses extracted VBAP demand history to learn demand patterns (seasonality, intermittency, distribution shape)
- Generates new `outbound_order` / `outbound_order_line` records at realistic rates
- Applies stochastic perturbation (the 21 distribution types already supported)
- Optionally injects demand signals (spikes, shifts, bursts — Powell's "styles of uncertainty")

**Layer 3 — Supply Event Generator** (simulates supplier/production activity)
- New PO receipts with stochastic lead times (fitted from EKBE history)
- Production completions with stochastic yields (fitted from AFRU history)
- Inventory movements (goods issues, adjustments, transfers)
- Supplier disruptions (delayed shipments, partial deliveries, quality holds)

**AAP Protocol — CDC Event Emitter** (triggers Autonomy's existing pipeline)
- Each generated event writes to the AWS SC tables (forecast, inv_level, inbound_order, etc.)
- Fires the same CDC signals that a real SAP integration would:
  - `CDCMonitor` detects metric deviations → triggers in `powell_cdc_trigger_log`
  - `OutcomeCollector` computes actual outcomes for TRM decisions
  - `CDTCalibrationService` recalibrates from decision-outcome pairs
  - `ConditionMonitorService` checks 6 real-time conditions

### 8.3 Architecture

```
┌─────────────────────────────────────────────┐
│  SAP Change Simulator Service               │
│                                             │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐ │
│  │ Demand   │  │ Supply   │  │ Disruption│ │
│  │Generator │  │Generator │  │ Generator │ │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘ │
│       │              │              │       │
│       ▼              ▼              ▼       │
│  ┌─────────────────────────────────────┐    │
│  │  CDC Event Emitter                  │    │
│  │  (writes to AWS SC tables +         │    │
│  │   fires CDC signals)               │    │
│  └────────────────┬────────────────────┘    │
└───────────────────┼─────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────────────┐
    │  Existing Autonomy CDC Pipeline   │
    │                                   │
    │  CDCMonitor → OutcomeCollector    │
    │  → CDTCalibration → Retraining   │
    │  → TRM Hive → Site tGNN          │
    └───────────────────────────────────┘
```

### 8.4 Disruption Scenarios

Predefined profiles for targeted testing:

| Scenario | Description | TRMs Tested |
|----------|-------------|-------------|
| **Steady State** | Normal demand/supply variation (baseline) | All |
| **Demand Spike** | 2-3x demand surge on select SKUs | ATP, Inventory Buffer |
| **Supplier Disruption** | Lead time doubles for a key vendor | PO Creation, Rebalancing |
| **Quality Event** | Yield drops 20% at a plant | Quality Disposition, MO Execution |
| **Bullwhip Amplification** | Demand signal amplifies through tiers | All (classic Beer Game effect) |

### 8.5 Clock Speed

| Mode | Ratio | 1 Simulated Day = | Use Case |
|------|-------|--------------------|----------|
| `1x` | Real-time | 1 real day | Long-running demos |
| `10x` | Accelerated | 2.4 hours | Training sessions |
| `100x` | Fast-forward | ~15 minutes | Quick validation |
| `1000x` | Turbo | ~1.5 minutes | AI training data generation |

### 8.6 Capability Comparison

| Capability | With SAP Running | With Simulator |
|-----------|-----------------|----------------|
| Master data extraction | Yes | No (already extracted) |
| Ongoing demand flow | Yes (real orders) | Yes (simulated from fitted distributions) |
| TRM decision-making | Yes | Yes (identical CDC triggers) |
| CDC relearning loop | Yes | Yes (same pipeline) |
| Disruption scenarios | Wait for real events | On-demand, repeatable |
| AI training data | Slow (real-time only) | Fast (1000x speed) |
| Cost | ~$3.12/hr | $0 |

### 8.7 Implementation

- **Service**: `backend/app/services/sap_change_simulator.py`
- **API**: `backend/app/api/endpoints/sap_change_simulator.py`
- **Schedule**: Configurable via API — on-demand or periodic tick

The simulator writes to the same DB tables and triggers the same events as a real SAP CDC feed. Autonomy's TRM Hive, GNN, and relearning pipeline cannot distinguish simulated events from real ones.

---

## 10. "Azirella" Demo Scripts

Pre-written prompts for the Azirella bar during live demos. Each prompt is tagged with its behavior:

- **STRAIGHT-THROUGH** — All required fields present; routes immediately to the target Powell layer with no clarification.
- **CLARIFICATION** — Missing one or more required fields; the clarification panel appears with follow-up questions the presenter answers live.

Use the **SAP official demo values** (TG11, FG126, customer 17100001) for SAP audiences, and **MZ bikes** (C900, M500, Bigmart) for supply chain planning audiences.

### 10.1 Drop-in Order (Kinaxis Standard Demo)

The classic Kinaxis demo scenario: a major customer places an unexpected large order, and you watch the ripple through the supply chain in real time. This is the single most important demo script.

**Setup**: Ensure the SAP IDES 1710 config is provisioned and the Decision Stream is open.

#### Script 1a — Drop-in Order (Straight-Through)

> **Prompt**: Bigmart just called — they need 500 C900 bikes delivered to Detroit in 2 weeks. This is a new fleet deal we can't lose. Increase production and prioritize ATP allocation for this order across all MZ City bike components at Plant 1710 for the next 4 weeks.

- **Behavior**: STRAIGHT-THROUGH
- **Reason**: "new fleet deal we can't lose" + "Bigmart just called"
- **Direction**: increase
- **Metric**: capacity + service_level
- **Magnitude**: implied (500 units = specific qty, system derives %)
- **Duration**: 4 weeks
- **Geography**: Plant 1710
- **Products**: C900 + all MZ City bike components
- **Target Layer**: Layer 2 (Site tGNN — single-site coordination)
- **TRMs triggered**: ATP Executor, MO Execution, PO Creation, Inventory Buffer

**What to show**: Decision Stream lights up within seconds — ATP allocation decisions, MO release recommendations for C900 assembly, PO creation for Frame-900 and Wheels-900 components, inventory buffer adjustments. Click Inspect on each to show the reasoning chain.

#### Script 1b — Drop-in Order (Clarification)

> **Prompt**: Bigmart needs 500 bikes in 2 weeks — rush order.

- **Behavior**: CLARIFICATION
- **Missing fields**: Product (which bikes?), Geography (which plant?), Reason (why prioritize?)
- **Clarification panel shows**:
  - "Which product? [Select: C900 / C950 / C990 / M500 / M525 / M550 / R100 / R200 / R300]"
  - "Which plant? [Select: Plant 1710 / Plant 1720]"
  - "Why should we prioritize this? [Text input]"
- **Presenter answers**: C900, Plant 1710, "New fleet deal, strategic account"
- **Then routes**: Same as 1a

**What to show**: The clarification flow itself — the system doesn't just guess, it asks the right questions. Point out that the reason field is always required because every directive is tracked for effectiveness.

---

### 10.2 Demand Disruption Scenarios

#### Script 2a — Demand Spike (Straight-Through)

> **Prompt**: Market intelligence from our cycling industry analyst: summer season demand for Mountain series bikes will be 25% above forecast for the next 8 weeks across all East Coast customers. Adjust forecasts and increase buffer levels accordingly.

- **Behavior**: STRAIGHT-THROUGH
- **Direction**: increase
- **Metric**: inventory (buffer) + service_level
- **Magnitude**: 25%
- **Duration**: 8 weeks
- **Products**: M500, M525, M550
- **Geography**: East Coast customers
- **TRMs triggered**: Forecast Adjustment, Inventory Buffer

#### Script 2b — Customer Cancellation (Clarification)

> **Prompt**: CostClub is canceling their R200 order.

- **Behavior**: CLARIFICATION
- **Missing fields**: Magnitude (how many units?), Duration (one-time or ongoing?), Reason (why?)
- **Clarification panel shows**:
  - "How many units? [Number]"
  - "Is this a one-time cancellation or are they ending the relationship? [Select: one-time / permanent]"
  - "What's the reason? [Text]"
- **Presenter answers**: 300 units, one-time, "Budget cuts at CostClub"

#### Script 2c — New Product Introduction (Straight-Through)

> **Prompt**: The board approved the E-Bike launch. Introduce MZ-FG-E100 at Plant 1710, target 100 units per week, launch in 6 weeks. We need to ramp up component sourcing immediately — this is our entry into the electric segment and the CEO is watching.

- **Behavior**: STRAIGHT-THROUGH
- **Direction**: increase
- **Metric**: capacity
- **Duration**: 6 weeks (ramp), then ongoing
- **Products**: MZ-FG-E100 (new)
- **Geography**: Plant 1710
- **TRMs triggered**: PO Creation (new components), MO Execution (new routing), Inventory Buffer (initial stock build)

---

### 10.3 Supply Disruption Scenarios

#### Script 3a — Supplier Delay (Straight-Through)

> **Prompt**: EV Parts Inc. just notified us that all open POs are delayed by 14 days due to a fire at their Texas facility. We need to activate backup suppliers and expedite any critical component orders for the next 3 weeks. Our Q2 delivery commitments to Skymart and Bigmart are at risk.

- **Behavior**: STRAIGHT-THROUGH
- **Direction**: reallocate
- **Metric**: lead_time + service_level
- **Duration**: 3 weeks
- **Geography**: Plant 1710 (EV Parts' customer)
- **Products**: All components sourced from EV Parts Inc.
- **TRMs triggered**: PO Creation (alternate sourcing), Order Tracking (exception detection), Inventory Rebalancing (cross-site transfers)

#### Script 3b — Quality Hold (Clarification)

> **Prompt**: Quality issue on Frame 900 — put it on hold.

- **Behavior**: CLARIFICATION
- **Missing fields**: Magnitude (how many units?), Geography (which plant/warehouse?), Reason (what defect?), Duration (how long?)
- **Clarification panel shows**:
  - "How many units affected? [Number]"
  - "At which location? [Select: Plant 1710 / 1711 / 1712 / 1720]"
  - "What is the defect? [Text]"
  - "Expected hold duration? [Select: 1 week / 2 weeks / 1 month / until resolved]"
- **Presenter answers**: 500 units, Plant 1710, "Weld cracks found in batch inspection", 2 weeks

#### Script 3c — Supplier Bankruptcy (Straight-Through)

> **Prompt**: WaveCrest Labs has declared bankruptcy effective immediately. All supply from WaveCrest is permanently lost. Activate all alternative sources, expedite transfers from Plant 1720 inventory, and raise safety stock levels on affected components by 30% for the next quarter. This is a critical supply chain risk event.

- **Behavior**: STRAIGHT-THROUGH
- **Direction**: increase (buffer) + reallocate (sourcing)
- **Metric**: inventory + service_level
- **Magnitude**: 30% buffer increase
- **Duration**: 1 quarter
- **TRMs triggered**: PO Creation, Inventory Rebalancing, Inventory Buffer, Subcontracting (make-vs-buy assessment)

---

### 10.4 Capacity & Production Scenarios

#### Script 4a — Capacity Loss (Straight-Through)

> **Prompt**: Plant 1710 Assembly Line A is down for emergency repairs — we've lost 40% of production capacity. Estimated 3-week recovery. Prioritize high-margin C900 and M500 models, defer low-priority R-series production, and evaluate subcontracting options for Frame assemblies. Customer impact must be minimized — our OTIF target is 95%.

- **Behavior**: STRAIGHT-THROUGH
- **Direction**: reallocate
- **Metric**: capacity + service_level
- **Duration**: 3 weeks
- **Geography**: Plant 1710
- **Products**: Prioritize C900, M500; defer R-series
- **TRMs triggered**: MO Execution (sequencing, deferral), Subcontracting, ATP Executor (re-allocate), Maintenance Scheduling

#### Script 4b — Yield Problem (Clarification)

> **Prompt**: Scrap rate is up on the C900 line.

- **Behavior**: CLARIFICATION
- **Missing fields**: Magnitude (by how much?), Duration (since when / how long?), Reason (root cause?), Geography (which plant?)
- **Clarification panel shows**:
  - "By how much has the scrap rate increased? [Number: %]"
  - "At which plant? [Select: Plant 1710 / Plant 1720]"
  - "What's causing the increase? [Text]"
  - "How long do you expect this to last? [Select: 1 week / 2 weeks / 1 month / unknown]"
- **Presenter answers**: 15%, Plant 1710, "New batch of raw material from alternate supplier", 4 weeks

---

### 10.5 Strategic / Executive Scenarios

#### Script 5a — Cost Reduction Mandate (Straight-Through)

> **Prompt**: The CFO wants a 12% reduction in total inventory holding cost across all sites over the next 6 months. We're overinvested in slow-moving R-series stock while C-series is turning too fast. Rebalance network inventory and tighten buffer levels on R-series while maintaining 95% service on C-series. This is a board-level commitment.

- **Behavior**: STRAIGHT-THROUGH
- **Direction**: decrease (cost) + reallocate (inventory)
- **Metric**: cost + inventory
- **Magnitude**: 12%
- **Duration**: 6 months
- **Geography**: All sites
- **Products**: R-series (tighten), C-series (maintain)
- **Target Layer**: Layer 4 (S&OP GraphSAGE — network-wide policy)

#### Script 5b — Service Level Target (Clarification)

> **Prompt**: We need better fill rates.

- **Behavior**: CLARIFICATION
- **Missing fields**: Magnitude (how much better?), Products (which ones?), Duration (by when?), Geography (which region?), Reason (why now?)
- **Clarification panel shows**:
  - "What fill rate target? [Number: %]"
  - "Which products? [Select: All / C-series / M-series / R-series]"
  - "Which region? [Select: All / East Coast / West Coast]"
  - "By when? [Select: 1 month / 1 quarter / 6 months]"
  - "What's driving this? [Text]"
- **Presenter answers**: 98%, C-series, All regions, 1 quarter, "Lost 3 key accounts to competitors with better availability"

---

### 10.6 Questions (Query Routing)

These are informational queries — they don't create directives but navigate to the right page with filters pre-applied.

> **"Show me all pending ATP decisions"**
> → Navigates to ATP Worklist (status: INFORMED)

> **"What's our inventory position on C900 bikes?"**
> → Navigates to Inventory Visibility (product: MZ-FG-C900)

> **"Any overdue POs from EV Parts?"**
> → Navigates to PO Worklist with supplier filter

> **"How's demand trending for Mountain bikes this quarter?"**
> → Navigates to Demand Plan View (product family: Mountain)

> **"Show me the supply chain network"**
> → Navigates to Supply Chain Config Sankey

> **"What did the AI decide about the Bigmart order?"**
> → Navigates to Decision Stream with Bigmart context injected

---

### 10.7 Demo Sequence — Recommended Order

For a 30-minute live demo, run these in order:

| # | Script | Time | Purpose |
|---|--------|------|---------|
| 1 | **1a** (Drop-in order, straight-through) | 5 min | Hero moment — show the full agentic response |
| 2 | **Question**: "Show me the supply chain network" | 2 min | Context — show the MZ Bikes topology |
| 3 | **3a** (Supplier delay, straight-through) | 5 min | Supply disruption — show cascading agent response |
| 4 | **4b** (Yield problem, clarification) | 4 min | Show the clarification flow — system asks, human answers |
| 5 | **Question**: "What's our inventory on C900?" | 1 min | Quick query routing |
| 6 | **2a** (Demand spike, straight-through) | 4 min | Demand disruption — forecast + buffer adjustment |
| 7 | **5a** (CFO cost reduction, straight-through) | 5 min | Strategic layer — show S&OP GraphSAGE response |
| 8 | **1b** (Drop-in order, clarification) | 4 min | Contrast with 1a — show incomplete vs complete |

**Key narrative arc**: Start with the "wow" moment (drop-in order handled in seconds), establish context (network view), then layer on disruptions to show resilience. End with strategic to show the full pyramid from execution to S&OP.

---

## 11. References

*(Renumbered from §10 after adding Azirella scripts)*

- [SAP S/4HANA FAA Demo Guides — SAP Community](https://community.sap.com/t5/technology-blog-posts-by-sap/sap-s-4hana-fully-activated-appliance-demo-guides/ba-p/13389412)
- [SAP S/4HANA FAA Getting Started Guide v21](SAP/Documentation/SAP_Getting_Started_Guide_v21.pdf) (local)
- [SAP S/4HANA 2025 FAA Known Issues](https://community.sap.com/t5/technology-blog-posts-by-sap/sap-s-4hana-2025-fully-activated-appliance-known-issues/ba-p/14260301)
- [SAP S/4HANA FAA Demo Guides & System Access — LinkedIn](https://www.linkedin.com/pulse/sap-s4hana-fully-activated-appliance-demo-guides-system-mh)
- [SAP DDMRP Functionality](https://blogs.sap.com/2019/02/17/s4hana-demand-driven-mrp-ddmrp-functionality/)
- [Demo Script: Transportation Mgmt Basic Outbound (FPS03)](https://www.sap.com/documents/2025/05/6e7a09ef-037f-0010-bca6-c68f7e60039b.html)
- [SAP Integration Guide](docs/external/SAP_INTEGRATION_GUIDE.md)
- [AWS SC Implementation Status](docs/internal/AWS_SC_IMPLEMENTATION_STATUS.md)
