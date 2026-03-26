# SAP Integration Guide
## S/4HANA and APO Supply Chain Data Integration

**Version**: 2.0
**Date**: 2026-03-18
**Status**: Implementation Ready

---

## Table of Contents

1. [Overview](#overview)
2. [AI-Enhanced Features](#ai-enhanced-features)
3. [Architecture](#architecture)
4. [Connection Modes](#connection-modes)
5. [Installation](#installation)
6. [Configuration](#configuration)
7. [Data Extraction](#data-extraction)
8. [AWS Supply Chain Mapping](#aws-supply-chain-mapping)
9. [Plan Writing](#plan-writing)
10. [Usage Examples](#usage-examples)
11. [Troubleshooting](#troubleshooting)
12. [SAP Table Reference](#sap-table-reference)

---

## Overview

The SAP Integration module enables bidirectional data exchange between Beer Game and SAP systems:

- **Extract** supply chain data from S/4HANA and APO
- **Map** to AWS Supply Chain Data Model format
- **Optimize** using Beer Game simulation engine
- **Write** optimized plans back to SAP

### Supported SAP Systems

- **SAP S/4HANA**: ERP with integrated supply chain (1909+)
- **SAP APO**: Advanced Planning and Optimization (7.0+)

### Connection Methods

1. **Direct RFC** (pyrfc): Real-time connection via SAP NetWeaver RFC
2. **CSV Files**: Batch mode using file-based extracts

### AI-Enhanced Capabilities (New)

The integration now includes **Claude AI-powered features** for intelligent data handling:

- **Z-Field Interpretation**: Automatic interpretation of custom SAP fields (Z*/ZZ* fields)
- **Missing Data Assistance**: AI recommendations for handling missing or unexpected data
- **Schema Validation**: Intelligent data quality checks with auto-fix suggestions
- **Delta Loading**: Efficient daily updates with net change detection (20x performance improvement)
- **Auto-Fixing**: Automatic application of AI-recommended data transformations

**For comprehensive AI features documentation, see**: [SAP_AI_INTEGRATION_GUIDE.md](SAP_AI_INTEGRATION_GUIDE.md)

---

## AI-Enhanced Features

### Overview

The SAP integration includes **intelligent loading capabilities** powered by Claude AI (Sonnet 4.5). These features automatically handle the most common challenges in SAP data integration:

1. **Custom Z-Fields**: SAP systems often extend standard tables with custom fields (starting with Z or ZZ). Claude AI automatically interprets these fields and suggests appropriate mappings.

2. **Data Quality Issues**: Missing values, unexpected data types, and schema mismatches are detected and fixed automatically with AI recommendations.

3. **Delta Loading**: Daily incremental loads transfer only changed records, achieving up to 99.5% reduction in data volume with hash-based and date-based change detection.

4. **Initial vs Daily Load**: Two distinct modes optimize for full data synchronization (initial) versus efficient updates (daily).

### Quick Start with AI Features

```bash
# Initial load with Claude AI (full extract with validation)
python backend/scripts/intelligent_sap_load.py \
    --mode initial \
    --source csv \
    --csv-dir /data/sap/csv \
    --claude

# Daily load (delta only with net change detection)
python backend/scripts/intelligent_sap_load.py \
    --mode daily \
    --source csv \
    --csv-dir /data/sap/csv \
    --claude
```

### Key Benefits

| Feature | Benefit | Performance Impact |
|---------|---------|-------------------|
| Z-Field Interpretation | No manual mapping configuration | Saves 2-4 hours per custom field |
| Auto-Fixing | Automatic data quality correction | 90%+ issues resolved automatically |
| Delta Loading | Transfer only changed records | 20x faster, 99.5% data reduction |
| Schema Validation | Early error detection | Prevents downstream failures |
| AI Recommendations | Expert-level data transformation suggestions | Reduces manual analysis time |

### Example: Z-Field Interpretation

```python
# Claude AI automatically interprets custom fields like:
# ZCUSTLEAD -> "Customer lead time in days"
# ZSAFETYSTK -> "Safety stock override quantity"
# ZVENDMAT -> "Vendor-specific material number"

from app.integrations.sap import create_intelligent_loader

loader = create_intelligent_loader(
    mode="initial",
    connection_type="csv",
    use_claude=True,
    claude_api_key="your-anthropic-api-key"
)

# AI automatically analyzes and maps Z-fields
df, result = loader.load_table("MARC", data_source)
print(f"Z-fields found: {result.z_fields_found}")
print(f"AI recommendations: {result.validation_analysis.claude_suggestions}")
```

### When to Use AI Features

**Use AI-Enhanced Loading When:**
- Working with heavily customized SAP systems (many Z-fields)
- Data quality is inconsistent or unknown
- Need to minimize daily data transfer volume
- Want automatic documentation of custom fields
- Require intelligent error handling

**Use Standard Loading When:**
- Simple, well-documented SAP systems
- No custom Z-fields or extensions
- Small datasets where delta loading isn't needed
- Cost optimization (AI features use Anthropic API)

### Configuration

Enable AI features by setting the Anthropic API key:

```bash
# In .env file
ANTHROPIC_API_KEY=sk-ant-your-api-key

# Or pass as command-line argument
--claude-api-key sk-ant-your-api-key
```

**For detailed AI features documentation, see**: [SAP_AI_INTEGRATION_GUIDE.md](SAP_AI_INTEGRATION_GUIDE.md)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      SAP Systems                             │
│                                                              │
│  ┌──────────────┐              ┌──────────────┐            │
│  │  S/4HANA     │              │     APO      │            │
│  │              │              │              │            │
│  │ - MARA/MARC  │              │ - /SAPAPO/   │            │
│  │ - EKKO/EKPO  │              │   LOC/MAT    │            │
│  │ - VBAK/VBAP  │              │ - SNP Plans  │            │
│  │ - LIKP/LIPS  │              │ - Orders     │            │
│  └──────────────┘              └──────────────┘            │
│         │                              │                    │
│         │  RFC or CSV                  │  CSV Primary       │
│         ▼                              ▼                    │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                Beer Game Integration Layer                   │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ S4HANA       │  │    APO       │  │     CSV      │     │
│  │ Connector    │  │  Connector   │  │   Loader     │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│         │                  │                  │            │
│         └──────────────────┴──────────────────┘            │
│                          │                                  │
│                          ▼                                  │
│              ┌──────────────────────┐                      │
│              │ Intelligent Loader   │ ◄── NEW              │
│              │ (Claude AI)          │                      │
│              │ - Z-Field Analysis   │                      │
│              │ - Schema Validation  │                      │
│              │ - Delta Loading      │                      │
│              │ - Auto-Fixing        │                      │
│              └──────────────────────┘                      │
│                          │                                  │
│                          ▼                                  │
│              ┌──────────────────────┐                      │
│              │  AWS Supply Chain    │                      │
│              │  Data Model Mapper   │                      │
│              └──────────────────────┘                      │
│                          │                                  │
│                          ▼                                  │
│              ┌──────────────────────┐                      │
│              │   Beer Game Engine   │                      │
│              │   (Optimization)     │                      │
│              └──────────────────────┘                      │
│                          │                                  │
│                          ▼                                  │
│              ┌──────────────────────┐                      │
│              │    Plan Writer       │                      │
│              │  (Back to SAP)       │                      │
│              └──────────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    SAP Systems (Write)                       │
│                                                              │
│  - Purchase Requisitions (BAPI_PR_CREATE)                   │
│  - Planned Orders (CSV Import)                              │
│  - Stock Transport Orders (BAPI_PO_CREATE1)                 │
│  - APO SNP Plans (CSV Upload)                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Connection Modes

### Mode 1: Direct RFC Connection

**Advantages:**
- Real-time data access
- Direct BAPI calls for writing
- No intermediate files

**Requirements:**
- SAP NetWeaver RFC SDK installed
- pyrfc Python library
- SAP user credentials with appropriate authorizations
- Network connectivity to SAP system

**Use Cases:**
- Real-time integration
- Automated scheduled jobs
- Production environments with SAP connectivity

### Mode 2: CSV File-Based

**Advantages:**
- No RFC dependencies
- Works with any SAP export
- Easier security/firewall configuration
- Can work offline

**Requirements:**
- CSV extracts from SAP (manual or scheduled)
- File system access to CSV directory

**Use Cases:**
- Development/testing
- Air-gapped environments
- APO integration (recommended due to liveCache complexity)
- Batch processing

---

## Getting Access to SAP S/4HANA (Free)

If you don't have an existing SAP system, you can deploy a fully-configured **S/4HANA Fully-Activated Appliance (FAA)** with IDES sample data for development and testing.

### Step 1: Create an SAP Account

1. Go to [https://account.sap.com/core/create/register](https://account.sap.com/core/create/register)
2. Fill in: First name, Last name, Email, Username, Password, Country
3. Accept terms, complete captcha, click **Register**
4. Verify your email — you now have an **SAP Universal ID**

This account is free and gives access to SAP Cloud Appliance Library, SAP Community, SAP Learning Hub, SAP BTP Trial, and SAP API Business Hub.

### Step 2: Deploy S/4HANA FAA via Cloud Appliance Library

1. Go to [cal.sap.com](https://cal.sap.com) and sign in with your SAP ID
2. Click **Appliances** → **Create**
3. Search for **"SAP S/4HANA Fully-Activated Appliance"**
4. Select it and choose a cloud provider (AWS, Azure, or GCP)
5. Link your cloud provider account (requires billing enabled)
6. Pick an instance size — smallest is sufficient for table extraction
7. Click **Create** — provisioning takes ~1-2 hours

**Cost**: You pay only the cloud provider for compute while the instance runs (~$1-3/hr depending on size). **Suspend or terminate when not in use.**

### Step 3: Connect to the Appliance

Once deployed, go to **Workloads → Appliances** in CAL. Click **Connect** on your appliance to see a dialog with connection options:

<!-- Screenshot: CAL Connect dialog showing RDP and SAP GUI options -->
<!-- SID: S4H, Instance Number: 00, Client: 100 -->

| Service | Target | Use |
|---------|--------|-----|
| **RDP** | Windows Remote Desktop | Access the Windows VM (SAP GUI is pre-installed) |
| **SAP GUI** | SID: S4H, Instance: 00 | Direct SAP GUI connection (requires SAP GUI installed locally) |

**Recommended: Use the RDP connection** — SAP GUI is already installed on the Windows VM. The SAP GUI `.sap` file download requires SAP GUI for Java on Linux (which can be difficult to configure), whereas the Windows VM inside the appliance has SAP GUI pre-installed and ready to use.

#### Connecting via RDP

1. Click **Connect** on the RDP row → downloads a `.rdp` file (e.g., `Autonomy.rdp`)
2. The `.rdp` file contains a simple connection definition:
   ```
   full address:s:<your-appliance-public-ip>
   username:s:Administrator
   ```
   > **Note**: The `s:` prefix is RDP file format syntax meaning "string type" — it is not part of the IP address or username.
3. Open with your RDP client:
   - **Linux**: `remmina -c ~/Downloads/Autonomy.rdp` (use the `-c` flag to connect directly; without it, Remmina may just display the file contents)
   - **Windows**: Double-click the `.rdp` file
   - **macOS**: Use Microsoft Remote Desktop
4. **Username**: `Administrator`
5. **Password**: The master password you set when creating the appliance in CAL

> **Important**: The CAL master password is for the **Windows VM only**. SAP application users have separate credentials (see below).

#### Logging into SAP GUI

Once on the Windows desktop, open **SAP Logon** (desktop shortcut or Start menu). The S4H system entry should already be configured.

<!-- Screenshot: SAP Logon screen showing SID: S4H, Instance: 00, Client: 100 -->

**SAP system login credentials** (different from the Windows/CAL password):

| User | Client | Default Password | Notes |
|------|--------|-----------------|-------|
| `SAP*` | 100 | `Down1oad` | Super admin — use for initial setup only |
| `BPINST` | 100 | `Welcome1` | Best Practices demo user |
| `DDIC` | 100 | `Down1oad` | Data dictionary admin |

> **Note**: Passwords are case-sensitive. The `1` in `Down1oad` and `Welcome1` is the **digit one**, not lowercase L. If `Down1oad` doesn't work, try `Initial1`.

**Available clients:**
- **Client 100**: Sandbox with demo data for US (merged-000) — **use this for Autonomy**
- **Client 200**: Best Practices ready-to-activate (BP client copy)
- **Client 400**: Best Practices fully-activated (BP client copy)

<!-- Screenshot: SAP login screen showing Client 100, available clients listed in the information panel -->

### Step 4: Create the Autonomy RFC User

**This step is required before Autonomy can connect to SAP.** You must create a dedicated technical user with the correct authorizations for RFC table reads and BAPI execution.

> **SAP User ID limit**: SAP user IDs are limited to **12 characters**. The examples below use `ZRFC_AUTONO` (truncated from `ZRFC_AUTONOMY`). SAP will silently truncate longer names.

#### 4a. Create the Authorization Role (Transaction PFCG)

1. Log in to SAP GUI as `SAP*` on **Client 100**
2. Enter **`/nPFCG`** in the command field (top-left input box) and press Enter
   > **Tip**: The `/n` prefix closes the current transaction before opening the new one. Use this when navigating between transactions.
3. Enter role name: **`ZRFC_AUTONOMY`** in the Role field and click **Single Role** (create button)
4. **Description tab**: Enter `Autonomy Platform RFC Integration` and click **Save**

<!-- Screenshot: PFCG role creation screen with description "Autonomy Platform RFC Integration" -->

5. Go to the **Authorizations** tab → click **Change Authorization Data**
6. If prompted to select a template, click **Do not select templates**
7. Click **Manually** (pencil icon in the toolbar) — a dialog opens with multiple Authorization Object input fields

**Enter all three authorization objects in the dialog** (you can add them all at once):

| Row | Authorization Object |
|-----|---------------------|
| 1 | `S_RFC` |
| 2 | `S_TABU_DIS` |
| 3 | `S_TABU_NAM` |

Click the **green checkmark** to confirm. You should see the objects appear in the tree view under their respective object classes:
- **Object class AAAB** (Cross-application Authorization Objects): `S_RFC`
- **Object class BC_A** (Basis: Administration): `S_TABU_DIS`, `S_TABU_NAM`

<!-- Screenshot: Authorization objects tree showing S_RFC under AAAB, S_TABU_DIS and S_TABU_NAM under BC_A -->

> **Note**: If you accidentally add the same object multiple times (e.g., S_TABU_DIS appears as Authorizat. 00, 01, 02), that's harmless — just set values on `Authorizat. 00` for each.

8. **Expand each object** by clicking the triangle/arrow icons and set the field values:

**S_RFC** — RFC access (expand → Authorizat. 00 → fields):

| Field | Value | Description |
|-------|-------|-------------|
| `RFC_TYPE` | `*` (All values) | Type of RFC object to which access is allowed |
| `RFC_NAME` | `*` | Name of RFC object (all function groups) |
| `ACTVT` | `16` (Execute) | Activity |

<!-- Screenshot: S_RFC expanded showing RFC_TYPE=All values, RFC_NAME=*, ACTVT=Execute -->

> **For production**: Restrict `RFC_NAME` to specific function groups: `SDTX`, `SYST`, `RFC1`, `BAPT`, `2012`. Using `*` is appropriate for development/test FAA systems.

**S_TABU_DIS** — Table read/write access (expand → Authorizat. 00 → fields):

| Field | Value | Description |
|-------|-------|-------------|
| `DICBERCLS` | `*` | Table Authorization Group (all groups) |
| `ACTVT` | `02, 03` (Change, Display) | Activity — include Change (`02`) if you need write-back to SAP |

> **For read-only access**: Set `ACTVT` to `03` (Display) only. For full integration with plan write-back (BAPI_PO_CREATE1, BAPI_PR_CREATE), include `02` (Change).

**S_TABU_NAM** — Table access by name (expand → Authorizat. 00 → fields):

| Field | Value | Description |
|-------|-------|-------------|
| `TABLE` | `*` | Table Name (all tables) |
| `ACTVT` | `02, 03` (Change, Display) | Activity — match S_TABU_DIS settings |

> **For production**: Restrict `TABLE` to the specific 47 tables Autonomy reads:
> ```
> MARA, MAKT, MARC, MARD, MARM, MBEW, MVKE,
> ADRC, T001, T001W, T001L,
> LFA1, KNA1,
> EINA, EINE, EORD, EBAN, EKKO, EKPO, EKET, EKBE,
> VBAK, VBAP, VBEP, VBUK, VBUP, LIKP, LIPS,
> AFKO, AFPO, AFVC, AFRU, AUFK, RESB, CRHD, PLKO, PLPO,
> STKO, STPO,
> PBIM, PBED, PLAF,
> LTAK, LTAP,
> QMEL, QALS, QASE,
> EQUI, MKPF, MSEG
> ```

9. Click **Save** (Ctrl+S or floppy disk icon)

<!-- Screenshot: All authorization objects expanded with values set, Data Status: Saved -->

10. **Generate the authorization profile**: Click the **Edit** dropdown button (near "Status" in the toolbar) → select **Activate Authorizations**

> **Important**: The "Generate" action in S/4HANA 2025 is accessed via the **Edit** dropdown → **Activate Authorizations**, not via a standalone traffic light button as in older SAP versions.

11. When prompted for a profile name, enter a name **without underscores** (SAP profile names have strict naming rules):
    - Profile name: **`ZRFCAUTONOMY`** (max 12 characters, no underscores)
    - Profile text: `Profile for role ZRFC_AUTONOMY` (auto-filled)
    - Click the green checkmark to confirm

> **Note**: Profile names that contain underscores (e.g., `Z_RFC_AUTO`) may be rejected as invalid in some S/4HANA versions. Use only alphanumeric characters.

12. Click **Back** (green arrow) to return to the main PFCG role screen
13. Verify the **Authorizations** tab now shows a green square (instead of yellow triangle) and the **Information About Authorization Profile** section shows:
    - Profile Name: `ZRFCAUTONOMY`
    - Status: `Authorization profile is current`

<!-- Screenshot: PFCG role main screen showing Profile Name: ZRFCAUTO, Status: Authorization profile is current -->

#### 4b. Create the Technical User (Transaction SU01)

1. Enter **`/nSU01`** in the command field and press Enter
2. Enter username: **`ZRFC_AUTONO`** (12 character limit) and click **Create** (page icon)

> **Important**: SAP truncates user IDs to 12 characters. `ZRFC_AUTONOMY` becomes `ZRFC_AUTONO`. Always use the truncated form.

3. Fill in the tabs:

**Address tab:**

| Field | Value |
|-------|-------|
| Last Name | `Autonomy RFC User` (or any descriptive name) |

<!-- Screenshot: SU01 Address tab with Last Name filled in, error messages at bottom prompting for password -->

> **Note**: When you first try to save, SAP will show error messages at the bottom: "Enter an initial password" and "You must specify the last name of a user". Fill in both the Last Name on the Address tab and the password on the Logon Data tab before saving.

**Logon Data tab** (click the tab):

| Field | Value |
|-------|-------|
| User Type | **System** (select from dropdown — this is type `B` for background/RFC) |
| Initial Password | Your chosen password |
| Repeat Password | Same password |

> **User Type B (System)**: Cannot log in interactively via SAP GUI. Can only be used for RFC/batch connections. This is the correct type for a technical integration user. Choose a strong password — this user will have broad table read access.

**Roles tab** (click the tab):

You can assign the role now or after creating the user. To assign:
1. Click in the **Role** column
2. Enter `ZRFC_AUTONOMY`
3. Press Enter to validate

> **Note**: If you haven't created the role yet (Step 4a), save the user without a role first. You can assign the role later via PFCG (User tab) or by returning to SU01.

4. Click **Save** (Ctrl+S)

#### 4c. Assign Role to User (via PFCG User Tab)

If you didn't assign the role in SU01, or to verify the assignment:

1. Enter **`/nPFCG`** → enter role `ZRFC_AUTONOMY` → click **Change** (pencil icon)
2. Click the **User** tab
3. Enter **`ZRFC_AUTONO`** in the User ID column
4. Click **User Comparison** button
5. Select **Full Comparison** and confirm
6. You should see: "Comparison of user master record completed" and "User master record for all roles adjusted"

<!-- Screenshot: PFCG User tab with ZRFC_AUTONO entered, User Comparison result showing successful comparison -->

7. Click **Save** (Ctrl+S)

#### 4d. Verify the User

1. Enter **`/nSU01`** → enter `ZRFC_AUTONO` → click **Display** (glasses icon)
2. Go to the **Profiles** tab — verify the authorization profile `ZRFCAUTONOMY` is listed
3. Go to the **Roles** tab — verify `ZRFC_AUTONOMY` is assigned

#### 4e. Test RFC Connectivity

From the Autonomy platform, configure the SAP connection:

```env
# .env or SAP Data Management UI
S4HANA_HOST=<your-appliance-public-ip>    # Public IP from CAL appliance details
S4HANA_SYSNR=00
S4HANA_CLIENT=100
S4HANA_USER=ZRFC_AUTONO
S4HANA_PASSWORD=<your-password>
```

Or test via the SAP Data Management page in the Autonomy admin UI:
1. Navigate to **Administration → SAP Data Management**
2. Click **Add Connection** → select **RFC** connection type
3. Enter the host (public IP from CAL), system number `00`, client `100`, and credentials
4. Click **Test Connection** — should return success with system info

> **Finding the public IP**: In CAL, go to **Workloads → Appliances** → click on your appliance name. The **Public IPv4 address** is shown in the appliance details panel (right side). You can also find it in the downloaded `.rdp` file (`full address:s:<ip>`).

### Step 5: Activate OData Services (Optional)

If using OData instead of or in addition to RFC, activate these services in SAP:

1. Enter **`/n/IWFND/MAINT_SERVICE`** in the command field
2. Click **Add Service** and search for each service:

| OData Service | Description |
|--------------|-------------|
| `API_PRODUCT_SRV` | Material master data |
| `API_MRP_MATERIALS_SRV_01` | MRP planning data |
| `API_PURCHASEREQ_PROCESS_SRV` | Purchase requisitions |
| `API_BUSINESS_PARTNER` | Vendors and customers |

3. For each: select it, assign to system alias `LOCAL`, and activate
4. Test via browser: `http://<host>:<port>/sap/opu/odata/sap/API_PRODUCT_SRV/$metadata`

The `ZRFC_AUTONO` user also needs `S_SERVICE` authorization object for OData access (add via PFCG → Manually):
- `SRV_NAME`: `*` (or specific service names)
- `SRV_TYPE`: `HT` (HTTP Service)

### Step 6: Extract Data

**Table extraction methods:**
- **Autonomy SAP Data Management UI** (recommended): Automated 3-phase pipeline (Master Data → CDC → Transactional)
- **SE16/SE16N** (SAP GUI): Browse and export individual tables (MARC, MDKP, PLAF, EBAN, PBIM, etc.)
- **OData APIs**: REST-based extraction (see Step 5)
- **CSV export** via SE16N → Download spreadsheet → use as input for CSV connection mode

### What's Included

The FAA comes pre-loaded with **IDES sample data** covering:
- Material master (MARA, MARC, MARD, MARM, MAKT)
- Organizational structure (T001, T001W, T001L, T024E)
- Purchasing (EKKO, EKPO, EINA, EINE, EBAN)
- Sales (VBAK, VBAP, KNA1, KNVV)
- Production (AFKO, AFPO, STKO, STPO, PLKO, PLPO)
- MRP (MDKP, MDTB, PLAF)
- Forecasting (PBIM, MPOP)
- Quality, Maintenance, Subcontracting, and more

All 56 SAP tables mapped in the platform (47 S/4HANA + 9 APO) are available for extraction and testing.

### Alternative Free Options

| Option | Access | Limitations |
|--------|--------|-------------|
| **SAP Learning Hub** (free tier) | Preconfigured sandbox, no cloud account needed | Limited hours, shared system |
| **SAP BTP Trial** ([account.hanatrial.ondemand.com](https://account.hanatrial.ondemand.com)) | ABAP environment | No full ERP, limited modules |
| **SAP Datasphere Sample Content** (GitHub) | CSV extracts of demo data | No live system, static data |

---

## Installation

### Prerequisites

```bash
# Python 3.10+
python --version

# Install core dependencies
cd backend
pip install pandas numpy

# For AI-enhanced features (recommended)
pip install anthropic

# Optional: For RFC connection (Mode 1)
# Requires SAP NetWeaver RFC SDK
pip install pyrfc
```

### SAP NetWeaver RFC SDK Installation (for RFC mode)

**Linux:**
```bash
# Download SDK from SAP Support Portal
# Extract to /usr/local/sap/nwrfcsdk

export SAPNWRFC_HOME=/usr/local/sap/nwrfcsdk
export LD_LIBRARY_PATH=$SAPNWRFC_HOME/lib:$LD_LIBRARY_PATH

pip install pyrfc
```

**Windows:**
```powershell
# Download SDK from SAP Support Portal
# Extract to C:\nwrfcsdk

$env:SAPNWRFC_HOME = "C:\nwrfcsdk"
$env:Path += ";C:\nwrfcsdk\lib"

pip install pyrfc
```

**macOS:**
```bash
# Download SDK from SAP Support Portal
# Extract to /usr/local/sap/nwrfcsdk

export SAPNWRFC_HOME=/usr/local/sap/nwrfcsdk
export DYLD_LIBRARY_PATH=$SAPNWRFC_HOME/lib:$DYLD_LIBRARY_PATH

pip install pyrfc
```

---

## Configuration

### Environment Variables

Create `.env` file:

```bash
# S/4HANA Connection (RFC Mode)
S4HANA_HOST=sap-s4hana.company.com
S4HANA_SYSNR=00
S4HANA_CLIENT=100
S4HANA_USER=ZRFC_AUTONO
S4HANA_PASSWORD=YourPassword

# APO Connection (CSV Mode Recommended)
APO_CSV_DIR=/data/sap/apo/exports

# Output Directory
SAP_OUTPUT_DIR=/data/sap/beergame/output

# AI-Enhanced Features (NEW)
ANTHROPIC_API_KEY=sk-ant-your-anthropic-api-key
```

### SAP User Permissions by Connection Type

> **Complete step-by-step setup instructions are in [Step 4: Create the Autonomy RFC User](#step-4-create-the-autonomy-rfc-user) above.**

**Quick Reference — Authorization objects for the `ZRFC_AUTONO` user (role `ZRFC_AUTONOMY`, profile `ZRFCAUTONOMY`):**

| Authorization Object | Values | Purpose |
|---------------------|--------|---------|
| `S_RFC` | `RFC_TYPE=*`, `RFC_NAME=*`, `ACTVT=16` | Execute all RFC function modules (`RFC_READ_TABLE`, BAPIs) |
| `S_TABU_DIS` | `DICBERCLS=*`, `ACTVT=02,03` | Read/write access to SAP tables by authorization group |
| `S_TABU_NAM` | `TABLE=*`, `ACTVT=02,03` | Read/write access to SAP tables by name |
| `S_SERVICE` | `SRV_TYPE=HT` | (Optional) OData service access |
| `S_DATASET` | File paths | (Optional) CSV export from SAP |

> **Production hardening**: For production deployments, restrict `*` values to specific function groups, table authorization groups, and table names. See Step 4a for the full list of 47 required tables.

Autonomy supports 4 connection types to SAP. Each requires different user setup and authorization. **Minimum privilege principle**: grant only what is needed for data extraction.

#### Connection Type 1: RFC (Remote Function Call)

**Recommended for**: Direct automated extraction from on-premise S/4HANA and ECC systems.

**User Setup**:
- Create a dedicated **Communication** user (type `C`) in client 100 via tCode `SU01`
- Recommended name: `ZRFC_AUTONOMY`
- Alternatively, unlock the pre-existing `BPINST` user (locked by default in FAA)
- Set password to never expire for automated jobs

**Required Authorization Objects**:

| Authorization Object | Field | Value | Purpose |
|---------------------|-------|-------|---------|
| **S_RFC** | RFC_TYPE | `FUGR` | Allow function group calls |
| | RFC_NAME | `SDTX`, `SDIFRUNTIME`, `RFC1`, `SYST` | RFC_READ_TABLE and dependencies |
| | ACTVT | `16` (Execute) | |
| **S_TABU_DIS** | ACTVT | `03` (Display) | Read access to SAP tables |
| | DICBERCLS | `*` (or restrict to specific table groups: `SC`, `SS`, `MM`, `SD`, `PP`, `QM`, `PM`) | Table authorization groups |
| **S_TABU_NAM** | ACTVT | `03` (Display) | Named table access (S/4HANA 1909+) |
| | TABLE | `MARA`, `MARC`, `MARD`, `MAKT`, `MBEW`, `MARM`, `MVKE`, `STKO`, `STPO`, `MAST`, `EORD`, `EINA`, `EINE`, `KNA1`, `KNVV`, `LFA1`, `VBAK`, `VBAP`, `EKKO`, `EKPO`, `AFKO`, `AFPO`, `AFRU`, `LIKP`, `LIPS`, `MSEG`, `MKPF`, `EKBE`, `CRHD`, `PLKO`, `PLPO`, `QALS`, `QMEL`, `JEST`, `PBIM`, `PBED`, `T001*`, `MARD`, `RESB`, `AUFK` | Specific tables for SC extraction |

**SAP Role Template**: Copy `SAP_BC_BATCH_DIALOG_RFC` and add `S_TABU_DIS`/`S_TABU_NAM`.

> **SAP Note 460089**: `RFC_READ_TABLE` has a 512-byte row buffer limit. The Autonomy extractor handles this automatically by reducing selected fields when the buffer overflows.

**Minimum SAP Tables Required** (70+ tables across 4 categories):
- **Master Data** (31 tables): MARA, MARC, MARD, MAKT, MBEW, MARM, MVKE, MAST, STKO, STPO, KNA1, KNVV, LFA1, EORD, EINA, EINE, EBAN, CRHD, EQUI, PLKO, PLPO, PBIM, PBED, PLAF, T001, T001W, T001L, ADRC, T179, KAKO, T024E
- **Transaction Data** (21 tables): VBAK, VBAP, VBEP, VBUK, VBUP, EKKO, EKPO, EKET, AFKO, AFPO, AFVC, AUFK, LIKP, LIPS, LTAK, LTAP, RESB, QMEL, QALS, QASE, KONV
- **CDC Data** (11 tables): MSEG, MKPF, EKBE, AFRU, JEST, TJ02T, MCH1, MCHA, CDHDR, CDPOS, CRCO
- **User Import** (7 tables): USR02, USR21, ADRP, AGR_USERS, AGR_DEFINE, AGR_1251, AGR_TCODES

#### Connection Type 2: OData API

**Recommended for**: SAP S/4HANA Cloud (Public Edition) where RFC is not available.

**User Setup**:
- Create a **Communication** user (type `C`) or use a **Service** user
- Assign the SAP standard business catalog `SAP_BASIS_TCR_T` for OData connectivity
- Alternatively, assign specific communication scenarios per OData service

**Required OData Services** (must be activated in tCode `/n/IWFND/MAINT_SERVICE`):

| OData Service | Purpose | Authorization |
|--------------|---------|---------------|
| `API_PRODUCT_SRV` | Material master data | Business catalog `SAP_MM_BC_PRODUCT_MDTRY_PC` |
| `API_BUSINESS_PARTNER` | Customer/vendor master | `SAP_CRM_BC_BUPA_MAINT_PC` |
| `API_PURCHASEORDER_PROCESS_SRV` | Purchase orders | `SAP_MM_BC_PO_MANAGE_PC` |
| `API_SALES_ORDER_SRV` | Sales orders | `SAP_SD_BC_SO_MANAGE_PC` |
| `API_PRODUCTION_ORDER_SRV` | Production orders | `SAP_PP_BC_MFG_ORDER_PC` |
| `API_PLANT_SRV` | Plant master data | `SAP_MM_BC_PRODUCT_MDTRY_PC` |

**Required Authorization Objects**:

| Object | Purpose |
|--------|---------|
| `S_SERVICE` | ICF service access (value: `/sap/opu/odata/*`) |
| `S_START` | Transaction start for OData gateway |

**ICF Nodes** (must be active in tCode `SICF`):
- `/sap/opu/odata/sap/` — OData service root
- `/sap/bc/sec/oauth2/token` — OAuth2 tokens (if using OAuth)

> **Note**: S/4HANA Cloud Public Edition uses Communication Arrangements (tCode `/n/SAPSLL/MON`) instead of ICF/OData activation. Consult SAP Cloud documentation for specific setup.

#### Connection Type 3: HANA DB Direct SQL

**Recommended for**: Bulk initial extraction and history loading. Fastest method (~10x faster than RFC).

**User Setup**:
- Create a dedicated HANA user via HANA Cockpit or SQL:
  ```sql
  CREATE USER AUTONOMY_EXTRACT PASSWORD "YourSecurePassword123!"
    NO FORCE_FIRST_PASSWORD_CHANGE;
  ```
- Grant read-only access to the ABAP schema:
  ```sql
  GRANT SELECT ON SCHEMA SAPHANADB TO AUTONOMY_EXTRACT;
  ```

**Minimum HANA Privileges**:

| Privilege | Object | Purpose |
|-----------|--------|---------|
| `SELECT` | Schema `SAPHANADB` | Read all SAP tables |
| `CATALOG READ` | System | List available tables/columns |

**Security Considerations**:
- HANA direct access bypasses ABAP authorization checks — use only for read operations
- Restrict to specific IP range via HANA `ALLOWED_SENDER` filter
- Consider creating a dedicated HANA schema user (not `SYSTEM`)
- Enable audit logging: `ALTER SYSTEM ALTER CONFIGURATION ('global.ini', 'SYSTEM') SET ('auditing configuration', 'global_auditing_state') = 'true'`

**Connection Parameters**:
- Default port: `302{instance}5` (e.g., `30215` for instance 02)
- Default schema: `SAPHANADB`
- SSL: Recommended for production (set `use_ssl=true`, provide HANA server certificate)

#### Connection Type 4: CSV File Upload

**Recommended for**: Customers who cannot allow direct system access (air-gapped, compliance-restricted).

**User Requirements** (for the SAP user who exports the CSVs):

| tCode | Purpose | Authorization |
|-------|---------|---------------|
| `SE16` / `SE16N` | Table display and download | `S_TABU_DIS` (ACTVT=03) |
| `SQVI` | QuickViewer for multi-table joins | `S_QUERY` |
| `/n/1BCDWB/DBACOCKPIT` | DB Browser (HANA only) | `S_ADMI_FCD` |
| `KE30` | Profitability reports (for cost data) | `S_DATASET` |

**Export Procedure**:
1. Login to SAP GUI (client 100)
2. Navigate to `SE16N`, enter table name (e.g., `MARA`)
3. Set selection criteria (e.g., WERKS = `1710`)
4. Execute, then use menu: List → Export → Spreadsheet → CSV
5. Save to the Autonomy import directory

**Batch Export** (recommended for large extractions):
- Use tCode `SM37` to schedule ABAP report `RSEPEXPORT` for automated table export
- Or use SAP GUI scripting with VBScript/Python to automate SE16N exports

**CSV File Naming Convention**:
- One file per SAP table: `{TABLE}.csv` (e.g., `MARA.csv`, `EKKO.csv`)
- Upload to: `imports/{TENANT_NAME}/{ERP_VARIANT}/{YYYY-MM-DD}/`
- The platform auto-detects SAP table names from filenames

**Minimum CSV Columns Required** (per table — the platform maps these to AWS SC entities):
- See [SAP Table Reference](#sap-table-reference) for required fields per table

---

> **Detailed Reference**: For complete authorization object specifications, role templates (PFCG), HANA privilege grants, and step-by-step user creation instructions, see [SAP User Permissions & Authorization Guide](../internal/SAP_USER_AUTHORIZATION_GUIDE.md).

### SAP FAA Setup — User Creation and Initial Configuration

> **Complete reference**: See [SAP_Cloud_Appliance_Library_Authorization.md](../knowledge/SAP_Cloud_Appliance_Library_Authorization.md) for the full list of all pre-existing accounts, passwords, ports, and ABAP clients.

The SAP S/4HANA Fully-Activated Appliance (FAA) requires initial setup before Autonomy can connect. The FAA comes with pre-configured accounts — you need to create **one dedicated extraction user**.

#### Pre-Existing Accounts (Already Available)

| User | Password | Purpose |
|------|----------|---------|
| **BPINST** | `Welcome1` | Generic technical user — works in all clients (000/100/200/400) |
| **SAP*** | `<Master Password>` | Super-admin — unlocked in client 100 only |
| **DDIC** | `<Master Password>` | Dictionary admin — unlocked in client 100 only |
| **SYSTEM** | `<Master Password>` | HANA database system user |
| **SAPHANADB** | `<Master Password>` | Technical HANA user — schema with all S/4HANA data |

The **Master Password** is what you set when creating the appliance in SAP CAL.

#### Step 1: Create Dedicated Autonomy Extraction User

Login to SAP GUI, **client 100**, as `BPINST` / `Welcome1`:

1. tCode **`SU01`** → User: `ZRFC_AUTONOMY` → **Create** (F8)
2. **Address tab**: Last name = `Autonomy Extraction`
3. **Logon Data tab**: User Type = **Communication (C)**, set a strong password
4. **Profiles tab**: Assign **`SAP_ALL`** (acceptable for trial/demo — gives full read access)
5. **Save** (Ctrl+S)

> This same ABAP user works for **both RFC and OData** connections.

#### Step 2: Create HANA DB Extraction User (Optional — for HANA Direct SQL)

Connect to HANA Tenant DB (HDB, instance 02) as `SYSTEM` / `<Master Password>`:

```sql
CREATE USER AUTONOMY_EXTRACT PASSWORD "YourSecurePassword!"
  NO FORCE_FIRST_PASSWORD_CHANGE;
GRANT SELECT ON SCHEMA SAPHANADB TO AUTONOMY_EXTRACT;
GRANT CATALOG READ TO AUTONOMY_EXTRACT;
```

> **Warning**: HANA Direct bypasses all ABAP authorization checks. Use only with this dedicated read-only user.

#### Step 3: Open MM Inventory Period

tCode **`MMPV`** in client 100 → set period to current month (required for goods movements).

#### Step 4: Activate OData Services (if using OData connection)

> **Why this is needed**: The S/4HANA FAA has OData services registered in the backend (IWBEP) but they are NOT published to the frontend gateway (IWFND) by default. The catalog returns 0 services until you explicitly add them. This is a one-time setup step that requires SAP GUI.

> **If you don't need OData**: Skip this step entirely. Use **HANA DB** connection instead — it's 10x faster, accesses the same data, and requires no service activation. HANA DB is the recommended extraction method for on-premise S/4HANA.

**Step 4a: Activate the OData Gateway ICF Node**

1. Login to SAP GUI → client **100** → user `BPINST` / `Welcome1` (or your admin user)
2. tCode **`SICF`**
3. In the selection screen: Service Name = `*`, click Execute (F8)
4. Navigate the tree: **default_host** → **sap** → **opu** → **odata** → **sap**
5. Right-click **sap** (the one under odata) → **Activate Service**
6. Also activate: **default_host** → **sap** → **opu** → **odata** → **IWFND** (if inactive)
7. Also activate: **default_host** → **sap** → **opu** → **odata** → **IWBEP** (if inactive)

**Step 4b: Register OData Services in the Frontend Gateway**

1. tCode **`/n/IWFND/MAINT_SERVICE`**
2. Click **Add Service** button (or menu: Service → Add Service)
3. In the popup:
   - System Alias: `LOCAL` (or leave blank for embedded gateway)
   - Technical Service Name: enter the service name (e.g., `API_PRODUCT_SRV`)
   - Click **Get Services** (magnifying glass)
4. Select the service from the list → click **Add Selected Services**
5. In the next dialog:
   - Package Assignment: `$TMP` (local object — fine for demo)
   - Click **Continue** (Enter)
6. Repeat for each service:

| # | Technical Service Name | Description | Used For |
|---|----------------------|-------------|----------|
| 1 | `API_PRODUCT_SRV` | Product Master | Materials (MARA/MARC/MAKT) |
| 2 | `API_BUSINESS_PARTNER` | Business Partner | Customers + Vendors |
| 3 | `API_PURCHASEORDER_PROCESS_SRV` | Purchase Orders | PO headers + items (EKKO/EKPO) |
| 4 | `API_SALES_ORDER_SRV` | Sales Orders | SO headers + items (VBAK/VBAP) |
| 5 | `API_PRODUCTION_ORDER_2_SRV` | Production Orders | Prod orders (AFKO/AFPO) |
| 6 | `API_BILL_OF_MATERIAL_SRV_01` | Bill of Materials | BOMs (STKO/STPO + parent material) |
| 7 | `API_PLANT_SRV` | Plants | Sites (T001W) |
| 8 | `API_MATERIAL_STOCK_SRV` | Material Stock | Inventory (MARD) |

**Step 4c: Verify**

After adding all services, test from a browser or curl:
```bash
curl -sk -u 'ZRFC_AUTONOM:<password>' \
  "https://<SAP_HOST>:44301/sap/opu/odata/sap/API_PRODUCT_SRV/A_Product?\$top=2&\$format=json"
```
You should see JSON with product data. If you still get 401, check the user's `S_SERVICE` authorization.

**Troubleshooting OData**:

| Symptom | Cause | Fix |
|---------|-------|-----|
| HTTP 401 on all endpoints | User lacks `S_SERVICE` authorization | Assign `SAP_ALL` profile or add `S_SERVICE` to the user's role in PFCG |
| HTTP 200 but empty results | Service not registered in IWFND gateway | Follow Step 4b above |
| HTTP 404 | ICF node not active | Follow Step 4a above |
| HTTP 403 | User locked or expired | Check user status in SU01 (UFLAG should be 0) |
| Catalog returns 0 services | Backend services exist but not published to frontend | Follow Step 4b — this is the most common FAA issue |

> **S/4HANA 2023+ Note**: Starting with S/4HANA 2023, SAP sets `ICF_NODE_LAYOUT = NONE` for OData V2 by default (simplified model). If you're on 2023+, services may be auto-activated. The FAA 2025 still requires manual activation as described above.

#### Connection Details for Autonomy

| Connection | User | Port | Notes |
|------------|------|------|-------|
| **RFC** | `ZRFC_AUTONOMY` | 3300 | SID=S4H, Instance=00, Client=100 |
| **OData** | `ZRFC_AUTONOMY` | 44301 (HTTPS) | Same ABAP user as RFC |
| **HANA DB** | `AUTONOMY_EXTRACT` | 30215 | Schema=SAPHANADB |
| **CSV** | (no user needed) | N/A | Manual export via SE16N |

Configure in Autonomy: **Administration > SAP Data Management > Add Connection** (login as `admin@sap_demo.com`).

#### ABAP Clients in the FAA

| Client | Purpose | Use For |
|--------|---------|---------|
| **100** | Trial & exploration with demo data (US, company 1710) | **Use this one** — has Fiori apps, Best Practices, sample data |
| **200** | Ready-to-activate (empty) | Activating your own Best Practices |
| **400** | Best Practices reference (43 localizations) | Comparing standard config |

#### Ports Summary

| Port | Service |
|------|---------|
| 3300 | SAP RFC (instance 00) |
| 3389 | Windows RDP |
| 44301 | Web Dispatcher / Fiori / OData (HTTPS) |
| 30215 | HANA SQL (tenant DB, instance 02) |
| 8443 | SAP Cloud Connector |

> **To reset master password**: SAP CAL → Instances → Select appliance → "Reset Password" (requires appliance restart)

---

## Data Extraction

### Standard vs Intelligent Loading

**Standard Loading** (Basic extraction):
- Direct table reads without validation
- Manual handling of Z-fields
- Full load every time
- See examples below

**Intelligent Loading** (AI-Enhanced):
- Automatic Z-field interpretation
- Schema validation and auto-fixing
- Delta loading for daily updates
- See [SAP_AI_INTEGRATION_GUIDE.md](SAP_AI_INTEGRATION_GUIDE.md)

### S/4HANA Extraction

#### Using RFC Connection

```python
from app.integrations.sap import S4HANAConnector, S4HANAConnectionConfig

# Configure connection
config = S4HANAConnectionConfig(
    ashost="sap-s4hana.company.com",
    sysnr="00",
    client="100",
    user="ZRFC_AUTONO",
    passwd="YourPassword"
)

# Extract data
with S4HANAConnector(config) as connector:
    # Master data
    plants = connector.extract_plants()
    materials = connector.extract_materials(plant="1000")
    inventory = connector.extract_inventory(plant="1000")

    # Transactional data
    from datetime import date, timedelta

    date_from = date.today() - timedelta(days=90)
    date_to = date.today()

    po_headers, po_items = connector.extract_purchase_orders(
        plant="1000",
        date_from=date_from,
        date_to=date_to
    )

    so_headers, so_items = connector.extract_sales_orders(
        sales_org="1000",
        date_from=date_from,
        date_to=date_to
    )
```

#### Using CSV Files

```python
from app.integrations.sap import CSVDataLoader

# Configure CSV directory
loader = CSVDataLoader(csv_directory="/data/sap/csv")

# List available tables
available_tables = loader.list_available_tables()
print(f"Available: {available_tables}")

# Load data
plants = loader.load_plants()
materials = loader.load_materials(with_plant_data=True)
inventory = loader.load_inventory()
po_headers, po_items = loader.load_purchase_orders()
so_headers, so_items = loader.load_sales_orders()
```

### APO Extraction (CSV Recommended)

```python
from app.integrations.sap import APOConnector, APOConnectionConfig

# Configure for CSV mode
config = APOConnectionConfig(
    csv_directory="/data/sap/apo/exports",
    use_csv_mode=True
)

with APOConnector(config) as connector:
    # Master data
    locations = connector.extract_locations()
    materials = connector.extract_materials()
    mat_locs = connector.extract_material_locations()

    # Planning data
    stock = connector.extract_stock()
    orders = connector.extract_orders()
    snp_plan = connector.extract_snp_plan(
        plan_version="000",
        date_from=date_from,
        date_to=date_to
    )
```

---

## AWS Supply Chain Mapping

### Mapping Overview

The AWS Supply Chain Data Model provides standardized entities for supply chain data:

| SAP Data | AWS Entity | Mapping |
|----------|------------|---------|
| T001W (Plants) | Sites | Physical locations |
| MARA/MARC (Materials) | Products | SKUs/Materials |
| MARD (Stock) | InventoryLevel | Stock positions |
| EKKO/EKPO (POs) | PurchaseOrder | Procurement |
| VBAK/VBAP (SOs) | SalesOrder | Customer orders |
| LIKP/LIPS (Deliveries) | Shipment | Shipments |
| APO Orders | SupplyPlan | Planned supply |
| APO SNP | DemandPlan | Demand forecast |

### Mapping Example

```python
from app.integrations.sap import AWSSupplyChainMapper

mapper = AWSSupplyChainMapper()

# Map S/4HANA data
aws_sites = mapper.map_s4hana_plants_to_sites(plants)
aws_products = mapper.map_s4hana_materials_to_products(materials)
aws_inventory = mapper.map_s4hana_inventory_to_inventory_levels(inventory)
aws_pos = mapper.map_s4hana_po_to_purchase_orders(po_headers, po_items)
aws_sos = mapper.map_s4hana_so_to_sales_orders(so_headers, so_items)

# Map APO data
aws_sites_apo = mapper.map_apo_locations_to_sites(locations)
aws_supply = mapper.map_apo_orders_to_supply_plans(orders)
aws_demand = mapper.map_apo_snp_to_demand_plans(snp_plan)

# Export to AWS format
mapper.export_to_aws_format(
    df=aws_products,
    entity_type="Products",
    output_path="aws_products.csv"
)
```

### AWS Supply Chain Entity Schemas

**Sites:**
```python
{
    "site_id": "1000",
    "site_name": "Hamburg Plant",
    "site_type": "PLANT",
    "country": "DE",
    "city": "Hamburg",
    "is_active": True
}
```

**Products:**
```python
{
    "product_id": "FG001",
    "product_name": "Finished Good 001",
    "product_category": "FERT",
    "unit_of_measure": "EA",
    "is_active": True
}
```

**InventoryLevel:**
```python
{
    "site_id": "1000",
    "product_id": "FG001",
    "inventory_date": "2026-01-16",
    "available_quantity": 500.0,
    "in_transit_quantity": 100.0,
    "safety_stock_quantity": 200.0
}
```

---

## Operational Statistics Extraction

### Overview

In addition to master and transactional data, the pipeline can extract **operational performance statistics** directly from SAP S/4HANA's HANA database. These statistics compute distribution parameters (mean, stddev, percentiles) for stochastic variables using HANA's in-memory columnar engine — avoiding the need to download millions of raw transaction rows.

### Stochastic Variables Extracted

13 aggregation queries compute summary statistics grouped by the appropriate business dimensions:

| Metric | SAP Tables | Grouping | Output |
|--------|-----------|----------|--------|
| Supplier lead time (days) | EKKO, EKBE | Vendor × Material × Plant | min, P05, P25, median, P75, P95, max, mean, stddev |
| Supplier on-time rate | EKBE, EKET | Vendor | Rate (0-1) |
| Supplier qty accuracy | EKBE, EKPO | Vendor × Material × Plant | Ratio received/ordered |
| Manufacturing cycle time | AFKO, AFPO, AFRU | Material × Plant | Days (release → final confirmation) |
| Manufacturing yield | AFRU, AFPO | Material × Plant | Ratio yield/(yield+scrap) |
| Manufacturing setup time | AFRU, AFPO | Material × Plant | Minutes |
| Manufacturing run time | AFRU, AFPO | Material × Plant | Minutes per unit |
| Machine MTBF | QMEL (type M2) | Equipment × Plant | Days between breakdowns (LAG window) |
| Machine MTTR | QMEL (type M2) | Equipment × Plant | Hours to repair |
| Quality rejection rate | QALS | Material × Plant | Rejected qty / lot size |
| Transportation lead time | LIKP, LIPS | Ship-from plant × Ship-to | Days (GI → POD) |
| Demand variability | VBAP | Material × Plant (weekly) | Weekly order quantity distribution |
| Order fulfillment time | VBAK, VBAP, LIPS, LIKP | Material × Plant × Customer | Days (order creation → delivery) |

### Usage

```bash
# Extract operational statistics only
python scripts/extract_sap_hana.py \
    --host 10.0.0.1 --port 30015 \
    --user SAPHANADB --password Secret123 \
    --company-code 1710 \
    --operational-stats

# Extract specific metrics
python scripts/extract_sap_hana.py \
    --operational-stats \
    --stats-metrics supplier_lead_time,manufacturing_yield,machine_mtbf
```

Output: `operational_stats.json` and per-metric CSV files in the output directory.

### Distribution Fitting

The mapper (`SupplyChainMapper.map_operational_stats_to_distributions()`) fits distributions from summary statistics:

- **Lognormal**: For right-skewed positive data (lead times, cycle times) — detected when median < mean or CV > 0.5
- **Beta**: For rate/ratio data bounded 0-1 (yields, on-time rates, rejection rates)
- **Normal**: For roughly symmetric data
- **Triangular**: Fallback when insufficient statistics (< 5 observations)

Distribution JSON is stored in `*_dist` columns (e.g., `vendor_lead_times.lead_time_dist`, `production_process.yield_dist`). A `NULL` value means "use the deterministic base field."

### Target Entity Columns

| Entity Table | `*_dist` Column | Source Metric |
|---|---|---|
| `vendor_lead_times` | `lead_time_dist` | supplier_lead_time |
| `production_process` | `operation_time_dist` | manufacturing_cycle_time |
| `production_process` | `setup_time_dist` | manufacturing_setup_time |
| `production_process` | `yield_dist` | manufacturing_yield |
| `production_process` | `mtbf_dist` | machine_mtbf |
| `production_process` | `mttr_dist` | machine_mttr |
| `transportation_lane` | `supply_lead_time_dist` | transportation_lead_time |

### Per-Agent Parameter Specialization

Beyond entity-level `*_dist` columns, the platform maintains per-agent stochastic parameters in the `agent_stochastic_params` table. When SAP operational statistics are imported:

1. Entity-level distributions update `*_dist` columns (as above)
2. Per-agent parameters can be derived from the same data, scoped to the specific TRM agent type that uses each variable
3. SAP-imported parameters are marked `source='sap_import'` and `is_default=False`, protecting them from being overwritten when the tenant's industry changes

This separation allows different agents to use different distribution assumptions for the same underlying variable — e.g., PO Creation may use a more conservative supplier lead time distribution than Order Tracking.

**API**: `GET /api/v1/agent-stochastic-params/?config_id=<id>` lists all per-agent parameters.
**UI**: Administration > Stochastic Parameters.

### Pipeline Settings (Configurable Extraction Thresholds)

SAP extraction thresholds are configurable per supply chain config via the `stochastic_config` JSON column on `supply_chain_configs`. This allows admins to tune how aggressively the system fits distributions from SAP transactional data.

| Setting | Default | Controls |
|---------|---------|----------|
| `min_observations` | 10 | Minimum observations per group for distribution fitting |
| `min_rows_sufficiency` | 50 | Minimum rows for data sufficiency pre-check (before expensive queries) |
| `cv_lognormal_threshold` | 0.5 | CV cutoff for lognormal vs normal selection |
| `min_group_count` | 3 | SQL HAVING COUNT per group in aggregation |

**Data sufficiency pre-check**: Before running expensive aggregation queries, `check_data_sufficiency()` runs lightweight COUNT queries against each metric's source tables. Metrics with fewer than `min_rows_sufficiency` rows are skipped entirely — downstream agent stochastic params fall back to industry defaults and are marked `source='industry_default'`.

**Admin UI**: Pipeline Settings panel at Administration > Stochastic Parameters. Shows current values, system defaults, and supports reset-to-defaults.

**API**:
- `GET /api/v1/agent-stochastic-params/pipeline-config/{config_id}`
- `PUT /api/v1/agent-stochastic-params/pipeline-config/{config_id}`

### Impact on Conformal Prediction

SAP-derived stochastic parameters improve conformal prediction **indirectly**, not directly. The relationship:

1. **SAP extraction** populates realistic distributions (lead times, yields, demand variability) from actual transactional history
2. These distributions feed **Monte Carlo simulation** (safety stock via `sl_fitted`/`econ_optimal` policies) and **TRM training** (digital twin scenario generation)
3. More realistic simulation → better TRM decisions → smaller prediction errors → **tighter conformal intervals**

Conformal prediction itself always calibrates from **real observations** (actual demand vs forecast, actual lead time vs predicted) — never from simulated data. This preserves the distribution-free coverage guarantee. The `sl_conformal_fitted` hybrid policy combines both: Monte Carlo precision from SAP-fitted distributions + conformal guarantee from real prediction errors.

---

## Plan Writing

### Writing Results Back to SAP

#### CSV Mode (Recommended)

```python
from app.integrations.sap import PlanWriter
from datetime import date, timedelta

# Initialize writer in CSV mode
writer = PlanWriter(
    output_directory="/data/sap/beergame/output",
    use_csv_mode=True
)

# Prepare optimization results
import pandas as pd

purchase_reqs = pd.DataFrame({
    "MATERIAL": ["FG001", "FG002"],
    "PLANT": ["1000", "1000"],
    "QUANTITY": [500, 300],
    "DELIV_DATE": [date.today() + timedelta(days=14)] * 2,
    "PREQ_PRICE": [10.0, 15.0],
    "CURRENCY": ["USD", "USD"],
    "PUR_GROUP": ["001", "001"]
})

# Write purchase requisitions
result = writer.write_purchase_requisitions(purchase_reqs)
print(f"Written: {result.records_written}")
print(f"Output: {result.output_file}")

# Write complete plan
plan_metadata = {
    "plan_version": "BG_20260116",
    "planning_horizon_start": date.today(),
    "planning_horizon_end": date.today() + timedelta(days=90),
    "created_by": "ZRFC_AUTONO",
    "description": "Beer Game Optimization"
}

optimization_results = {
    "purchase_requisitions": purchase_reqs,
    "planned_orders": planned_orders_df,
    "stock_transfers": sto_df,
    "snp_plan": snp_df
}

results = writer.write_beer_game_optimization_plan(
    optimization_results,
    plan_metadata
)
```

#### RFC Mode (Direct BAPI)

```python
from app.integrations.sap import PlanWriter, S4HANAConnector

# Establish connection
with S4HANAConnector(config) as connector:
    # Initialize writer with RFC connection
    writer = PlanWriter(
        connection=connector.connection,
        use_csv_mode=False
    )

    # Write purchase requisitions via BAPI
    result = writer.write_purchase_requisitions(
        purchase_reqs,
        test_mode=False  # Set True for validation only
    )

    # Check results
    for msg in result.messages:
        print(msg)
```

### APO SNP Plan Upload

```python
# APO always uses CSV mode
writer = PlanWriter(
    output_directory="/data/sap/apo/upload",
    use_csv_mode=True
)

snp_plan = pd.DataFrame({
    "LOCATION": ["DC01", "DC02"],
    "MATERIAL": ["FG001", "FG001"],
    "PLAN_DATE": [date.today() + timedelta(days=i) for i in range(2)],
    "DEMAND_QTY": [100, 120],
    "SUPPLY_QTY": [110, 130],
    "STOCK_QTY": [200, 210]
})

result = writer.write_apo_snp_plan(
    snp_plan=snp_plan,
    plan_version="001",
    planning_horizon_start=date.today(),
    planning_horizon_end=date.today() + timedelta(days=90)
)

print(f"SNP plan file: {result.output_file}")
# Then upload to APO via /SAPAPO/SNP94 transaction
```

---

## Usage Examples

### Example 1: Complete Integration Flow

```python
#!/usr/bin/env python3
"""Complete SAP integration example."""

from app.integrations.sap import (
    CSVDataLoader,
    AWSSupplyChainMapper,
    PlanWriter
)
from datetime import date, timedelta

# Step 1: Extract data from CSV
loader = CSVDataLoader("/data/sap/csv")
materials = loader.load_materials(with_plant_data=True)
inventory = loader.load_inventory()
po_headers, po_items = loader.load_purchase_orders()

# Step 2: Map to AWS format
mapper = AWSSupplyChainMapper()
aws_products = mapper.map_s4hana_materials_to_products(materials)
aws_inventory = mapper.map_s4hana_inventory_to_inventory_levels(inventory)
aws_pos = mapper.map_s4hana_po_to_purchase_orders(po_headers, po_items)

# Step 3: Run Beer Game optimization
# (Integrate with your Beer Game engine here)
optimization_results = run_beer_game_optimization(
    products=aws_products,
    inventory=aws_inventory,
    orders=aws_pos
)

# Step 4: Write results back to SAP
writer = PlanWriter(
    output_directory="/data/sap/output",
    use_csv_mode=True
)

plan_metadata = {
    "plan_version": "BG_" + date.today().strftime("%Y%m%d"),
    "planning_horizon_start": date.today(),
    "planning_horizon_end": date.today() + timedelta(days=90),
    "created_by": "ZRFC_AUTONO",
    "description": "Automated Beer Game Plan"
}

results = writer.write_beer_game_optimization_plan(
    optimization_results,
    plan_metadata
)

print("Integration complete!")
for component, result in results.items():
    print(f"{component}: {result.records_written} records written")
```

### Example 2: Using Command-Line Script (Standard Loading)

```bash
# Using CSV mode
python backend/scripts/sap_integration_example.py \
    --mode csv \
    --csv-dir /data/sap/csv \
    --output-dir /data/sap/output

# Using RFC mode
python backend/scripts/sap_integration_example.py \
    --mode rfc \
    --s4-host sap-s4hana.company.com \
    --s4-sysnr 00 \
    --s4-client 100 \
    --s4-user ZRFC_AUTONO \
    --s4-passwd YourPassword \
    --output-dir /data/sap/output
```

### Example 2b: Using Intelligent Loading (AI-Enhanced)

```bash
# Initial load with Claude AI (full extract with validation)
python backend/scripts/intelligent_sap_load.py \
    --mode initial \
    --source csv \
    --csv-dir /data/sap/csv \
    --claude \
    --report-dir /data/sap/reports

# Daily delta load (net change only)
python backend/scripts/intelligent_sap_load.py \
    --mode daily \
    --source csv \
    --csv-dir /data/sap/csv \
    --claude \
    --report-dir /data/sap/reports \
    --delta-state-dir /data/sap/delta_state

# RFC connection with AI
python backend/scripts/intelligent_sap_load.py \
    --mode daily \
    --source rfc \
    --s4-host sap-s4hana.company.com \
    --s4-user ZRFC_AUTONO \
    --s4-passwd YourPassword \
    --claude \
    --tables MARA MARC MARD EKKO EKPO

# Reset delta state (force full reload next time)
python backend/scripts/intelligent_sap_load.py \
    --mode daily \
    --source csv \
    --csv-dir /data/sap/csv \
    --reset-delta
```

### Example 3: Scheduled Batch Job (Standard)

```bash
#!/bin/bash
# sap_integration_job.sh

# Set up environment
export SAP_CSV_DIR=/data/sap/csv
export SAP_OUTPUT_DIR=/data/sap/output
export LOG_DIR=/var/log/beergame

# Run integration
python3 /app/backend/scripts/sap_integration_example.py \
    --mode csv \
    --csv-dir $SAP_CSV_DIR \
    --output-dir $SAP_OUTPUT_DIR \
    >> $LOG_DIR/integration_$(date +%Y%m%d).log 2>&1

# Archive old logs
find $LOG_DIR -name "integration_*.log" -mtime +30 -delete
```

Schedule with cron:
```cron
# Run daily at 2 AM
0 2 * * * /path/to/sap_integration_job.sh
```

### Example 3b: Scheduled Intelligent Job (AI-Enhanced)

```bash
#!/bin/bash
# intelligent_sap_load_job.sh

# Set up environment
export SAP_CSV_DIR=/data/sap/csv
export ANTHROPIC_API_KEY=sk-ant-your-api-key
export REPORT_DIR=/data/sap/reports
export DELTA_STATE_DIR=/data/sap/delta_state
export LOG_DIR=/var/log/beergame

# Timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Run intelligent loading (daily mode with delta)
python3 /app/backend/scripts/intelligent_sap_load.py \
    --mode daily \
    --source csv \
    --csv-dir $SAP_CSV_DIR \
    --claude \
    --report-dir $REPORT_DIR \
    --delta-state-dir $DELTA_STATE_DIR \
    >> $LOG_DIR/intelligent_load_${TIMESTAMP}.log 2>&1

# Check exit code
if [ $? -eq 0 ]; then
    echo "Load completed successfully at $(date)" >> $LOG_DIR/success.log
else
    echo "Load failed at $(date)" >> $LOG_DIR/errors.log
    # Send alert
    mail -s "SAP Load Failed" admin@company.com < $LOG_DIR/intelligent_load_${TIMESTAMP}.log
fi

# Archive old logs and reports
find $LOG_DIR -name "intelligent_load_*.log" -mtime +30 -delete
find $REPORT_DIR -name "validation_report_*.json" -mtime +90 -delete
```

Schedule with cron:
```cron
# Initial load: First day of month at 1 AM
0 1 1 * * export MODE=initial && /path/to/intelligent_sap_load_job.sh

# Daily delta load: Every day at 2 AM
0 2 * * * export MODE=daily && /path/to/intelligent_sap_load_job.sh
```

---

## Troubleshooting

### Common Issues

#### RFC Connection Fails

**Error:** `pyrfc.RFCError: Cannot connect to SAP system`

**Solutions:**
1. Check network connectivity: `ping sap-host.company.com`
2. Verify SAP system is running
3. Check firewall rules for RFC ports (33XX)
4. Verify credentials and authorizations
5. Test with SAP GUI first

#### CSV Files Not Found

**Error:** `CSV file not found for table: MARA`

**Solutions:**
1. Check CSV directory path is correct
2. Verify CSV files exist: `ls /data/sap/csv/*.csv`
3. Check file naming conventions (MARA.csv, SAP_MARA.csv, etc.)
4. Ensure read permissions on CSV files

#### Data Mapping Errors

**Error:** `Missing expected fields in MARA: ['MAKTX']`

**Solutions:**
1. Check SAP table extract includes all required fields
2. Review field mapping in `AWSSupplyChainMapper`
3. Update `expected_fields` list if schema changed
4. Use custom field mapping if needed

#### BAPI Call Fails

**Error:** `BAPI_PR_CREATE failed: Material XYZ not found`

**Solutions:**
1. Verify material exists in SAP
2. Check material is valid for plant
3. Ensure purchasing data maintained (MARC)
4. Run in test mode first: `test_mode=True`
5. Check SAP user authorizations

#### AI Features Issues

**Error:** `anthropic.APIError: Invalid API key`

**Solutions:**
1. Check ANTHROPIC_API_KEY is set correctly
2. Verify API key is active in Anthropic console
3. Test API key: `curl -H "x-api-key: $ANTHROPIC_API_KEY" https://api.anthropic.com/v1/messages`

**Error:** `Z-fields not interpreted`

**Solutions:**
1. Ensure `--claude` flag is enabled
2. Check that Z-fields have sample data (not all NULL)
3. Review validation report for AI analysis results
4. Increase AI token limit if hitting rate limits

**Error:** `Delta loading not working`

**Solutions:**
1. Check delta state directory exists and is writable
2. Verify change date fields exist in table (AEDAT, LAEDA, etc.)
3. Review delta state JSON files in delta_state_dir
4. Use `--reset-delta` to force full reload
5. Ensure key fields are properly defined for hash comparison

### Debugging Tips

**Enable debug logging:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

**Validate data before writing:**
```python
# Check DataFrame before writing
print(purchase_reqs.info())
print(purchase_reqs.head())

# Validate AWS schema
mapper = AWSSupplyChainMapper()
is_valid = mapper.validate_schema(aws_products, mapper.PRODUCT_SCHEMA)
print(f"Schema valid: {is_valid}")
```

**Test with small datasets:**
```python
# Limit rows for testing
materials_sample = materials.head(10)
aws_products = mapper.map_s4hana_materials_to_products(materials_sample)
```

**Debug AI features:**
```python
# Enable verbose logging for AI assistant
from app.integrations.sap import create_intelligent_loader
import logging

logging.basicConfig(level=logging.DEBUG)

loader = create_intelligent_loader(
    mode="initial",
    connection_type="csv",
    use_claude=True,
    save_reports=True  # Saves detailed validation reports
)

# Check validation report
import json
with open('/data/sap/reports/validation_report_MARC.json') as f:
    report = json.load(f)
    print(json.dumps(report, indent=2))
```

**Monitor delta loading performance:**
```python
from app.integrations.sap import SAPDeltaLoader, DeltaLoadConfig

loader = SAPDeltaLoader(state_directory="/data/sap/delta_state")

# Check what's in delta state
state = loader.tracker.get_last_load_timestamp("MARA")
print(f"Last load: {state}")

# View delta statistics
config = DeltaLoadConfig(
    table_name="MARA",
    key_fields=["MATNR"],
    change_date_field="LAEDA"
)

result = loader.load_delta(current_data, config)
print(f"New: {result.new_records}, Changed: {result.changed_records}")
print(f"Efficiency: {result.efficiency_metric:.2%} reduction")
```

---

## SAP Table Reference

### S/4HANA Core Tables

| Table | Description | Key Fields |
|-------|-------------|------------|
| **MARA** | Material Master (General) | MATNR, MAKTX, MTART, MEINS |
| **MARC** | Material Master (Plant) | MATNR, WERKS, DISPO, EISBE, PLIFZ |
| **MARD** | Material Master (Storage Location) | MATNR, WERKS, LGORT, LABST |
| **EKKO** | Purchasing Document Header | EBELN, LIFNR, BEDAT, EKORG |
| **EKPO** | Purchasing Document Item | EBELN, EBELP, MATNR, MENGE |
| **EKET** | Scheduling Agreement Schedule Lines | EBELN, EBELP, ETENR, EINDT |
| **VBAK** | Sales Document Header | VBELN, KUNNR, ERDAT, VKORG |
| **VBAP** | Sales Document Item | VBELN, POSNR, MATNR, KWMENG |
| **LIKP** | Delivery Header | VBELN, LFDAT, WADAT_IST |
| **LIPS** | Delivery Item | VBELN, POSNR, MATNR, LFIMG |
| **T001W** | Plants/Branches | WERKS, NAME1, KUNNR, LIFNR |
| **T001L** | Storage Locations | WERKS, LGORT, LGOBE |

### APO Core Tables

| Table | Description | Key Fields |
|-------|-------------|------------|
| **/SAPAPO/LOC** | Locations | LOCNO, LOCDESC, LOCTYPE |
| **/SAPAPO/MAT** | Materials | MATNR, MATDESC, MATTYPE |
| **/SAPAPO/MATLOC** | Material-Location | MATNR, LOCNO, SAFETY_STOCK |
| **/SAPAPO/ORD** | Orders | ORDERNO, ORDERTYPE, MATNR, QUANTITY |
| **/SAPAPO/STOCK** | Stock/Inventory | MATNR, LOCNO, AVAILABLE_QTY |
| **/SAPAPO/SNP** | SNP Planning Data | PLAN_VERSION, MATNR, LOCNO, DEMAND_QTY |

### Execution & Quality Tables (New)

| Table | Description | Key Fields | SyncDataType |
|-------|-------------|------------|--------------|
| **LTAK** | Transfer Order Header | LGNUM, TESSION | `transfer_orders` |
| **LTAP** | Transfer Order Item | LGNUM, TESSION, TAESSION | `transfer_orders` |
| **QMEL** | Quality Notification Header | QMNUM, QMART, MATNR | `quality_orders` |
| **QMIH** | Quality Notification Item | QMNUM, FEESSION | `quality_orders` |
| **AUFK_PM** | Maintenance Order Header (PM) | AUFNR, EQUNR, ILART | `maintenance_orders` |
| **IHPA** | PM Object Partners | OBJNR, PESSION | `maintenance_orders` |
| **MHIS** | Maintenance History | OBJNR, POINT | `maintenance_orders` |
| **MKAL** | Subcontracting Cockpit | MATNR, WERKS, VEESSION | `subcontracting_orders` |
| **EKKO_SC** | Subcontracting PO Header (doc type L) | EBELN, BSART='L' | `subcontracting_orders` |
| **EKPO_SC** | Subcontracting PO Item | EBELN, EBELP | `subcontracting_orders` |

### Standard BAPIs

| BAPI | Purpose | Parameters |
|------|---------|------------|
| **BAPI_PR_CREATE** | Create Purchase Requisition | PRHEADER, PRITEM |
| **BAPI_PO_CREATE1** | Create Purchase Order/STO | POHEADER, POITEM, POSHIPPING |
| **BAPI_TRANSACTION_COMMIT** | Commit BAPI Changes | WAIT |
| **RFC_READ_TABLE** | Read SAP Table | QUERY_TABLE, FIELDS, OPTIONS |

---

## Appendix A: CSV File Formats

### Expected CSV Formats

#### Materials (MARA.csv)
```csv
MATNR,MAKTX,MTART,MEINS,MATKL,BRGEW,NTGEW,GEWEI,VOLUM,VOLEH
FG001,Finished Good 001,FERT,EA,MAT01,10.5,9.5,KG,0.05,M3
FG002,Finished Good 002,FERT,EA,MAT01,12.0,11.0,KG,0.06,M3
```

#### Inventory (MARD.csv)
```csv
MATNR,WERKS,LGORT,LABST,UMLME,INSME,SPEME
FG001,1000,0001,500,100,0,0
FG002,1000,0001,300,50,0,0
```

#### Purchase Orders Header (EKKO.csv)
```csv
EBELN,BUKRS,BSTYP,BSART,LIFNR,EKORG,EKGRP,BEDAT
4500001234,1000,F,NB,VENDOR01,1000,001,20260115
```

#### Purchase Orders Item (EKPO.csv)
```csv
EBELN,EBELP,MATNR,WERKS,LGORT,MENGE,MEINS,NETPR
4500001234,00010,FG001,1000,0001,500,EA,10.00
```

---

## Appendix B: Makefile Targets

Add to `Makefile`:

```makefile
# SAP Integration Targets

.PHONY: sap-extract-csv
sap-extract-csv: ## Extract SAP data from CSV files
	docker compose exec backend python -m scripts.sap_integration_example \\
		--mode csv \\
		--csv-dir /data/sap/csv \\
		--output-dir /data/sap/output

.PHONY: sap-extract-rfc
sap-extract-rfc: ## Extract SAP data via RFC
	docker compose exec backend python -m scripts.sap_integration_example \\
		--mode rfc \\
		--s4-host ${S4HANA_HOST} \\
		--s4-sysnr ${S4HANA_SYSNR} \\
		--s4-client ${S4HANA_CLIENT} \\
		--s4-user ${S4HANA_USER} \\
		--s4-passwd ${S4HANA_PASSWORD}

.PHONY: sap-test-connection
sap-test-connection: ## Test SAP RFC connection
	docker compose exec backend python -c \\
		"from app.integrations.sap import S4HANAConnector, S4HANAConnectionConfig; \\
		import os; \\
		config = S4HANAConnectionConfig( \\
			ashost=os.getenv('S4HANA_HOST'), \\
			sysnr=os.getenv('S4HANA_SYSNR'), \\
			client=os.getenv('S4HANA_CLIENT'), \\
			user=os.getenv('S4HANA_USER'), \\
			passwd=os.getenv('S4HANA_PASSWORD') \\
		); \\
		conn = S4HANAConnector(config); \\
		print('Testing connection...'); \\
		result = conn.connect(); \\
		print(f'Connection: {'SUCCESS' if result else 'FAILED'}'); \\
		conn.disconnect()"

.PHONY: sap-intelligent-load
sap-intelligent-load: ## Run intelligent SAP load with Claude AI
	docker compose exec backend python scripts/intelligent_sap_load.py \\
		--mode daily \\
		--source csv \\
		--csv-dir /data/sap/csv \\
		--claude \\
		--report-dir /data/sap/reports \\
		--delta-state-dir /data/sap/delta_state

.PHONY: sap-initial-load
sap-initial-load: ## Run initial full SAP load
	docker compose exec backend python scripts/intelligent_sap_load.py \\
		--mode initial \\
		--source csv \\
		--csv-dir /data/sap/csv \\
		--claude \\
		--report-dir /data/sap/reports

.PHONY: sap-reset-delta
sap-reset-delta: ## Reset delta state (force full reload)
	docker compose exec backend python scripts/intelligent_sap_load.py \\
		--mode daily \\
		--source csv \\
		--csv-dir /data/sap/csv \\
		--reset-delta
```

---

## Building a SupplyChainConfig from SAP Data

The SAP Config Builder creates a complete SupplyChainConfig (sites, products, lanes, BOMs, sourcing rules, forecasts, inventory) from extracted SAP tables. This is the **reverse path** — importing SAP data into the platform's AWS SC data model.

### 8-Step Build Pipeline

| Step | Name | SAP Tables Used | Entities Created |
|------|------|-----------------|------------------|
| 1 | **Data Validation** | All loaded tables | Config record (validates MARA/MARC + T001W minimum) |
| 2 | **Geography** | ADRC | Geography (addresses, lat/lon, country, city) |
| 3 | **Sites** | T001W, /SAPAPO/LOC | Site (with master type inference) |
| 4 | **Products** | MARA, MARC, MVKE, MARM | Product (with hierarchy and UOM) |
| 5 | **Transportation Lanes** | /SAPAPO/TRLANE, EORD, EKPO, LIKP/LIPS | TransportationLane (priority cascade) |
| 6 | **Partners & Sourcing** | LFA1, KNA1, EINA, EINE, EORD | TradingPartner, VendorProduct, VendorLeadTime, SourcingRules |
| 7 | **BOM & Manufacturing** | STPO, STKO, PLKO, PLPO | ProductBom, ProductionProcess |
| 8 | **Planning Data** | /SAPAPO/SNPFC, /SAPAPO/SNPBV, MARD | Forecast, InvLevel, InvPolicy |

### Master Type Inference

Sites are automatically classified into one of four master types based on SAP data patterns:

- **MANUFACTURER**: Plant has BOM production entries (STPO components linked via MARC)
- **MARKET_SUPPLY**: Site code appears as vendor in LFA1
- **MARKET_DEMAND**: Site code appears as customer in KNA1
- **INVENTORY**: Default for sites with inventory data (MARD) but no BOM/vendor/customer role

Users can override inferred master types in the wizard UI.

### Transportation Lane Inference (Priority Cascade)

When explicit APO lane data is unavailable, lanes are inferred from transactional data:

1. **APO TRLANE** (highest confidence): Explicit transportation lane definitions
2. **EORD Source List**: Approved vendor → plant assignments
3. **Historical EKPO**: Purchase order patterns (vendor + plant with ≥3 POs)
4. **Historical LIKP/LIPS**: Delivery flow patterns (plant → customer with ≥3 deliveries)

### Z-Table and Z-Field Integration

During validation (Step 1), the builder detects any Z-prefixed tables or unknown custom tables. For each:
- Row count and field inventory are displayed
- AI-powered entity suggestion identifies the likely AWS SC target entity
- Users can toggle Z-tables for inclusion in the build process
- Field mapping uses the existing SAP Field Mapping Service for fuzzy matching

### Step-by-Step Wizard UI

The wizard (accessible at **Navigation → SAP Config Builder**) provides:

- **Progressive execution**: Each step can be executed individually
- **Three control options** after each step: Stop Here, Continue to Next, Continue to End
- **Anomaly detection**: Per-step data quality checks with severity levels (error/warning/info)
- **Suggested actions**: Each anomaly includes a remediation suggestion
- **Master type override**: Step 3 shows an editable table for correcting inferred site types
- **Planning configuration**: Step 8 allows setting inventory policy type, safety stock days, and forecast horizon

### API Reference

```
# Start build (Step 1: validate + create config)
POST /api/v1/sap-data/build-config/start
  Body: { connection_id, config_name, company_filter?, plant_filter? }
  Returns: StepResult with table_inventory, anomalies, z_tables

# Execute individual step
POST /api/v1/sap-data/build-config/{config_id}/step/{step_number}
  Body: { connection_id, master_type_overrides?, options? }
  Returns: StepResult with entities_created, sample_data, anomalies

# Complete all remaining steps
POST /api/v1/sap-data/build-config/{config_id}/complete
  Body: { connection_id, master_type_overrides?, options? }
  Returns: { config_id, config_name, summary }

# Check build status
GET /api/v1/sap-data/build-config/{config_id}/status
  Returns: { config_id, completed_steps, entity_counts }

# Delete partial/complete build
DELETE /api/v1/sap-data/build-config/{config_id}

# Full preview (dry-run, no DB changes)
POST /api/v1/sap-data/build-config/preview
  Body: { connection_id, config_name, company_filter?, plant_filter? }

# Full build (all steps at once)
POST /api/v1/sap-data/build-config
  Body: { connection_id, config_name, master_type_overrides?, options? }
```

### Anomaly Detection Summary

| Step | Anomaly Checks |
|------|---------------|
| Validation | Missing required tables, small datasets (<5 rows), null key fields |
| Geography | Missing country codes, missing city names |
| Sites | Zero-product sites, ambiguous master type inference |
| Products | Missing descriptions (MAKTX), missing base UOM |
| Lanes | No lead time data, low-confidence inferred lanes, missing endpoints |
| Partners | No source list, no purchasing info records, zero-price records |
| BOM | Components not in product master, missing BOM headers |
| Planning | No forecast data, no inventory data, high proportion of zero inventory |

---

## Support and Resources

### Documentation
- **[SAP_AI_INTEGRATION_GUIDE.md](SAP_AI_INTEGRATION_GUIDE.md)** - Comprehensive AI features documentation
- [SAP S/4HANA Documentation](https://help.sap.com/s4hana)
- [SAP APO Documentation](https://help.sap.com/apo)
- [AWS Supply Chain Data Model](https://docs.aws.amazon.com/aws-supply-chain/)
- [pyrfc Documentation](https://sap.github.io/PyRFC/)
- [Anthropic Claude API](https://docs.anthropic.com/)

### Contact
- Beer Game Support: See repository maintainers
- SAP Issues: SAP Support Portal
- pyrfc Issues: https://github.com/SAP/PyRFC/issues

---

## Related Documentation

- **[SAP_AI_INTEGRATION_GUIDE.md](SAP_AI_INTEGRATION_GUIDE.md)**: Comprehensive guide for AI-enhanced features including Z-field interpretation, delta loading, schema validation, and auto-fixing
- **[TRM_IMPLEMENTATION_PLAN.md](TRM_IMPLEMENTATION_PLAN.md)**: Implementation plan for Tiny Recursive Models as Beer Game agents

---

**Document Version**: 1.2
**Last Updated**: 2026-02-21
**Status**: Production Ready (with AI enhancements + Config Builder)
