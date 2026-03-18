# SAP User Permissions & Authorization Guide

## Required Authorizations for Autonomy Platform Data Extraction

**Version**: 1.0 | **Date**: 2026-03-18 | **Status**: Reference

This document specifies the exact SAP user permissions, authorization objects, roles, and minimum privilege requirements for each of the four connection types supported by the Autonomy platform.

---

## Table of Contents

1. [Connection Type 1: RFC (Remote Function Call)](#1-rfc-remote-function-call)
2. [Connection Type 2: OData API](#2-odata-api)
3. [Connection Type 3: HANA DB Direct SQL](#3-hana-db-direct-sql)
4. [Connection Type 4: CSV Export](#4-csv-export)
5. [FAA User Management](#5-faa-user-management)
6. [Creating a Dedicated Extraction User](#6-creating-a-dedicated-extraction-user)
7. [Security Best Practices](#7-security-best-practices)
8. [Quick Reference Matrix](#8-quick-reference-matrix)

---

## 1. RFC (Remote Function Call)

### Overview

The RFC connection uses the `RFC_READ_TABLE` (or `BBP_RFC_READ_TABLE`) function module to read SAP table data remotely. This is the primary connection method for the Autonomy platform, connecting on port 3300 (system number 00).

### Required Authorization Objects

#### 1.1 S_RFC — RFC Access Control

Controls which RFC function modules/groups the user can execute.

| Field | Value | Description |
|-------|-------|-------------|
| `RFC_TYPE` | `FUGR` | Object type: Function Group |
| `RFC_NAME` | See table below | Function group name |
| `ACTVT` | `16` | Activity: Execute |

**Required RFC_NAME values:**

| RFC_NAME | Purpose |
|----------|---------|
| `SDTX` | Table read framework (contains `RFC_READ_TABLE`) |
| `SYST` | System information (RFC metadata, system ID, version) |
| `SDIFRUNTIME` | Data dictionary runtime (table structure metadata) |
| `RFC1` | RFC communication foundation |
| `SRFC` | RFC function management |
| `BAPT` | BAPI transaction commit/rollback (if write-back needed) |
| `SH` | Search help (for field validation) |

> **SAP Note 460089**: Defines the minimum authorization profile for external RFC programs. Specifies required S_RFC entries by user type and system release. Available on SAP Service Marketplace (login required).

#### 1.2 S_TABU_DIS — Table Access by Authorization Group

Controls read access to tables by their authorization group (broad access).

| Field | Value | Description |
|-------|-------|-------------|
| `ACTVT` | `03` | Activity: Display (read-only) |
| `DICBERCLS` | See table below | Table authorization group |

**Required authorization groups for Autonomy extraction:**

| DICBERCLS | Tables Covered | Purpose |
|-----------|---------------|---------|
| `SC` | MARA, MARC, MARD, MAKT | Material master |
| `ME` | EKKO, EKPO, EINA, EINE, EORD, EKET | Purchasing |
| `SD` | VBAK, VBAP, LIKP, LIPS, KNA1, KNVV | Sales & distribution |
| `PP` | AFKO, AFPO, STPO, STKO, MAST, CRHD | Production planning |
| `PM` | AUFK, IHPA, MHIS | Plant maintenance |
| `BC` | T001W, T001, T001L | Customizing/basis |
| `MM` | MSEG, MKPF | Material movements |
| `LF` | LFA1 | Vendor master |
| `QM` | QALS | Quality management |
| `&NC&` | Miscellaneous tables without explicit group | Fallback group |

> **Note**: From SAP_BASIS 7.50+, `S_TABU_NAM` is checked FIRST, then `S_TABU_DIS`. For tighter security, use S_TABU_NAM to allow only specific tables.

#### 1.3 S_TABU_NAM — Table Access by Table Name (Preferred)

Controls read access to specific named tables (granular, more secure than S_TABU_DIS).

| Field | Value | Description |
|-------|-------|-------------|
| `ACTVT` | `03` | Activity: Display (read-only) |
| `TABLE` | Individual table names | Specific table to authorize |

**Minimum table list for Autonomy extraction:**

Phase 1 — Master Data:
```
MARA, MAKT, MARC, MARD, T001W, T001, T001L,
STPO, STKO, MAST, EINA, EINE, EORD,
LFA1, KNA1, KNVV, CRHD
```

Phase 2 — Transactional Data:
```
VBAK, VBAP, EKKO, EKPO, EKET,
AFKO, AFPO, LIKP, LIPS,
LTAK, LTAP, AUFK
```

Phase 3 — Historical Data:
```
EKBE, MSEG, MKPF, AFRU, AFVC,
QALS, KONV, PBIM, PBED
```

Data Dictionary Metadata (always needed):
```
DD02V, DD03L, DD04T, DD17S, DD27S, ENLFDIR
```

#### 1.4 S_TABU_CLI — Client-Independent Table Access

Required only for tables without an MANDT (client) column. Most Autonomy-relevant tables are client-dependent, so this is rarely needed.

| Field | Value | Description |
|-------|-------|-------------|
| `CLIIDMAINT` | `X` | Allow access to client-independent tables |

#### 1.5 Additional Authorization Objects

| Object | Field | Value | Purpose |
|--------|-------|-------|---------|
| `S_DATASET` | `ACTVT` = `33`, `PROGRAM` = `*`, `FILENAME` = `*` | File system access (if using server-side file export) |
| `S_BTCH_JOB` | `JOBACTION` = `RELE`, `JOBGROUP` = `*` | Background job scheduling (batch extraction) |

### Recommended Role Template

Create a custom role `ZRFC_AUTONOMY_READ` via PFCG:

```
Role Name:     ZRFC_AUTONOMY_READ
Description:   Autonomy Platform - RFC Read Access
Authorization Objects:
  S_RFC:        RFC_TYPE=FUGR, RFC_NAME=SDTX;SYST;SDIFRUNTIME;RFC1, ACTVT=16
  S_TABU_NAM:   ACTVT=03, TABLE=<all tables listed above>
  S_TABU_DIS:   ACTVT=03, DICBERCLS=SC;ME;SD;PP;PM;BC;MM;LF;QM;&NC&
```

### Standard SAP Roles (NOT Recommended)

| Role | Issue |
|------|-------|
| `SAP_ALL` | Full system access — massive security risk, never use in production |
| `SAP_NEW` | Broad access to new features — too permissive |
| `S_A.SCON` | RFC communication profile — does not include table-level access |

> **Recommendation**: Always create a custom Z-role with minimum required authorizations. Never assign SAP_ALL to an extraction user.

### User Creation Steps

1. Log into SAP GUI as user with `SU01` authorization (e.g., DDIC in client 000)
2. tCode `SU01` > Enter username `ZRFC_AUTONOMY` > Click Create
3. **Address tab**: First/Last name = "Autonomy", "RFC Service"
4. **Logon Data tab**:
   - User Type: **Communication** (type `C`) — dialog logon disabled, supports password change
   - Initial Password: Set a strong password (minimum 8 chars, mixed case + number + special)
   - Client: `100` (IDES demo data client)
5. **Roles tab**: Assign role `ZRFC_AUTONOMY_READ`
6. **Profiles tab**: Verify generated profile includes all authorization objects
7. Save

### Recommended User Type: Communication (C)

| User Type | Code | Dialog Login | Password Expiry | Best For |
|-----------|------|-------------|-----------------|----------|
| **Dialog** | `A` | Yes | Yes (default 90 days) | Interactive human users |
| **Communication** | `C` | No | Yes (follows system policy) | RFC between systems (recommended) |
| **System** | `B` | No | No (never expires) | Background jobs, internal RFC |
| **Service** | `S` | Yes (anonymous) | No (never expires) | ITS/web service endpoints |

**Communication** is recommended because:
- Prevents accidental dialog logon via SAP GUI
- Password expiry ensures credential rotation
- Explicitly designed for system-to-system RFC communication
- If password rotation is not desired (e.g., unattended extraction), use **System** (B) type instead

### Password Policy

| Parameter | Recommended Value | Profile Parameter |
|-----------|------------------|-------------------|
| Minimum length | 8 characters | `login/min_password_lng` |
| Password expiry | 180 days for Communication, 0 (never) for System | `login/password_expiration_time` |
| Failed login locks | 5 attempts | `login/fails_to_user_lock` |
| Complexity | Upper + lower + digit + special | `login/min_password_specials` |

---

## 2. OData API

### Overview

OData (Open Data Protocol) provides RESTful access to SAP data via HTTP/HTTPS. SAP S/4HANA exposes hundreds of OData V2 and V4 services for business entities. Connection via port 44301 (HTTPS) or 8443 (Cloud Connector).

### Required Authorization Objects

#### 2.1 S_SERVICE — ICF Service Authorization

Controls access to individual OData services.

| Field | Value | Description |
|-------|-------|-------------|
| `SRV_NAME` | Service technical name (IWSV or IWSG entry) | The OData service name |
| `SRV_TYPE` | `HT` | HTTP service type |

#### 2.2 IWSV — Individual OData Service Authorization

Each activated OData V2 service has an IWSV repository entry in SU22/SU24. The role must include IWSV entries for each service the user needs to access.

#### 2.3 IWSG — OData Service Group Authorization

Service groups aggregate multiple services. The role must include IWSG entries in addition to IWSV entries. Standard roles like `SAP_UI2_USER_700` include only IWSV entries — IWSG entries must be added manually.

#### 2.4 Additional Objects

| Object | Purpose |
|--------|---------|
| `S_RFCACL` | RFC access control list (if OData service calls RFC internally) |
| `S_START` | Transaction start authorization (for underlying business logic) |
| Business-specific objects | e.g., `M_BEST_EKO` for PO access, `V_VBAK_AAT` for sales order access |

### Required OData Services for Autonomy

#### Supply Chain Master Data

| OData Service | Version | Description | SAP Tables Behind |
|---------------|---------|-------------|-------------------|
| `API_PRODUCT_SRV` | V2 | Product/Material master | MARA, MARC, MARD, MAKT |
| `API_BUSINESS_PARTNER` | V2/V4 | Business partners (customers, vendors) | KNA1, LFA1, BP tables |
| `API_BILL_OF_MATERIAL_SRV` | V2 | Bill of Materials | STPO, STKO, MAST |
| `API_PLANT_SRV` | V2 | Plant/Site master | T001W |

#### Transactional Data

| OData Service | Version | Description | SAP Tables Behind |
|---------------|---------|-------------|-------------------|
| `API_SALES_ORDER_SRV` | V2 | Sales orders | VBAK, VBAP |
| `API_PURCHASEORDER_PROCESS_SRV` | V2 | Purchase orders (deprecated 2308, not decommissioned) | EKKO, EKPO |
| `API_INBOUND_DELIVERY_SRV` | V2 | Inbound deliveries / GR | LIKP, LIPS |
| `API_OUTBOUND_DELIVERY_SRV` | V2 | Outbound deliveries | LIKP, LIPS |
| `API_PRODUCTION_ORDER_2_SRV` | V2 | Production orders | AFKO, AFPO |
| `API_MATERIAL_STOCK_SRV` | V2 | Inventory/stock levels | MARD |
| `API_MRP_MATERIALS_SRV` | V2 | MRP data | MARC (MRP views) |

#### Planning Data

| OData Service | Version | Description |
|---------------|---------|-------------|
| `API_PLANNED_INDEPENDENT_RQMT_SRV` | V2 | Planned independent requirements (demand) |
| `API_SOURCELIST_SRV` | V2 | Source lists / sourcing rules |
| `API_PURCHASING_INFO_RECORD_SRV` | V2 | Vendor info records |

### ICF Node Activation

ICF (Internet Communication Framework) nodes must be active for OData to function.

**Activation via tCode SICF:**

| ICF Path | Purpose | Status Required |
|----------|---------|-----------------|
| `/sap/opu/odata/sap/` | OData V2 service root | Active (green) |
| `/sap/opu/odata4/sap/` | OData V4 service root | Active (green) |
| `/sap/bc/sec/oauth2/` | OAuth2 token endpoint (if using OAuth) | Active (green) |
| `/sap/public/bc/sec/login` | Login handler | Active (green) |
| `/sap/bc/webdynpro/` | WebDynpro (Fiori launchpad) | Active (if using Fiori) |

> **S/4HANA 2023+**: OData V2 services are set to `ICF Node = NONE` (no individual ICF node per service). OData V4 services never had individual ICF nodes. Both use the shared `/sap/opu/odata/` and `/sap/opu/odata4/` root nodes.

**Service activation via tCode /IWFND/MAINT_SERVICE:**

1. Open `/IWFND/MAINT_SERVICE`
2. Click "Add Service" > Enter system alias (e.g., `LOCAL`)
3. Search for the service name (e.g., `API_PRODUCT_SRV`)
4. Select the service > Click "Add Selected Services"
5. Verify ICF node status shows green (active)

### Read-Only Access Pattern

To grant read-only access to all relevant OData services:

1. Create role `ZODATA_AUTONOMY_READ` via PFCG
2. In the **Menu** tab, add each OData service via:
   - "Insert Node" > "SAP Gateway OData V2 Service" > search and add each service
   - This auto-populates S_SERVICE, IWSV, and IWSG entries
3. In the **Authorizations** tab:
   - Set all `ACTVT` fields to `03` (Display) only
   - Remove any `01` (Create), `02` (Change), `06` (Delete) activities
4. Generate the profile
5. Assign to the OData extraction user

### User Creation Steps

1. tCode `SU01` > Create user `ZODATA_AUTONOMY`
2. User Type: **Service** (S) — allows HTTP login without dialog, no password expiry
3. Assign role `ZODATA_AUTONOMY_READ`
4. Set initial password

> **Alternative User Type**: If password expiry is desired, use **Dialog** (A) type. Service type is preferred for OData because it does not expire and supports anonymous HTTP access patterns.

### Password Policy

Same as RFC (Section 1), plus:

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `icf/set_HTTPonly_flag_on_cookies` | `0` (or `3` for secure) | HTTP cookie security |
| `login/accept_sso2_ticket` | `1` | SSO ticket acceptance (if using SSO) |

---

## 3. HANA DB Direct SQL

### Overview

Direct SQL connection to the SAP HANA database on port 30215 (indexserver). Bypasses the ABAP application layer entirely — reads directly from HANA tables. This is the fastest extraction method but carries significant security implications.

### HANA User Privileges

#### 3.1 Schema-Level SELECT Privilege

The minimum privilege for data extraction is SELECT on the ABAP schema.

```sql
-- Connect to HANA as SYSTEM or schema owner
-- Create dedicated extraction user
CREATE USER AUTONOMY_EXTRACT PASSWORD '<strong_password>' NO FORCE_FIRST_PASSWORD_CHANGE;

-- Grant SELECT on the ABAP schema (SAPHANADB for FAA)
GRANT SELECT ON SCHEMA "SAPHANADB" TO AUTONOMY_EXTRACT;
```

This grants read access to ALL tables in the SAPHANADB schema. For more restrictive access, grant SELECT on individual tables:

```sql
-- Granular: individual table grants
GRANT SELECT ON "SAPHANADB"."MARA" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."MARC" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."MARD" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."MAKT" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."T001W" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."STPO" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."STKO" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."MAST" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."EINA" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."EINE" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."EORD" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."LFA1" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."KNA1" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."VBAK" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."VBAP" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."EKKO" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."EKPO" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."EKET" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."AFKO" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."AFPO" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."LIKP" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."LIPS" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."EKBE" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."MSEG" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."AFRU" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."AFVC" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."QALS" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."KNVV" TO AUTONOMY_EXTRACT;
GRANT SELECT ON "SAPHANADB"."KONV" TO AUTONOMY_EXTRACT;
-- Add more tables as needed
```

#### 3.2 Predefined HANA Roles

| Role | Access Level | Recommended? |
|------|-------------|--------------|
| `PUBLIC` | Basic metadata, system views | Automatically granted to all non-restricted users |
| `MONITORING` | Full read-only metadata + system/monitoring views + statistics server data | Useful for monitoring, NOT for business data |
| `SAP_INTERNAL_HANA_SUPPORT` | Full system access | NEVER grant — SAP support only |
| `CONTENT_ADMIN` | Repository content management | Not needed for extraction |

> **None of the predefined roles grant SELECT on business data schemas.** A custom role or explicit GRANT is always required for SAPHANADB table access.

#### 3.3 Custom HANA Role (Recommended)

```sql
-- Create a read-only extraction role
CREATE ROLE AUTONOMY_EXTRACTION_ROLE;

-- Grant schema-level SELECT
GRANT SELECT ON SCHEMA "SAPHANADB" TO AUTONOMY_EXTRACTION_ROLE;

-- Optionally grant catalog access for metadata queries
GRANT CATALOG READ TO AUTONOMY_EXTRACTION_ROLE;

-- Assign role to user
GRANT AUTONOMY_EXTRACTION_ROLE TO AUTONOMY_EXTRACT;
```

### Do NOT Use SAPHANADB User

The `SAPHANADB` user is the **schema owner** with full DDL/DML privileges on all ABAP tables. Using it for extraction is a critical security violation:

- It can CREATE, ALTER, DROP tables
- It can INSERT, UPDATE, DELETE data
- Compromised credentials would allow full database destruction

**Always create a dedicated user with SELECT-only access.**

### User Creation Methods

#### Via HANA Cockpit (Web UI)

1. Open HANA Cockpit: `https://<HANA_HOST>:30215` (or HANA Studio port 30213)
2. Navigate to Security > User Management
3. Click "Create User"
4. Username: `AUTONOMY_EXTRACT`
5. Authentication: Password (set strong password)
6. Deselect "Force password change on first logon" for service accounts
7. Assign role `AUTONOMY_EXTRACTION_ROLE`
8. Save

#### Via HANA Studio (Eclipse)

1. Connect to HANA system in HANA Studio
2. Expand Security > Users
3. Right-click > "New User"
4. Configure as above

#### Via SQL (DBACOCKPIT or HANA SQL Console)

```sql
-- From ABAP: tCode DBACOCKPIT > SQL Console
-- From HANA: HANA Studio SQL Console or hdbsql CLI

CREATE USER AUTONOMY_EXTRACT PASSWORD 'Aut0n0my!Extr4ct#2026' NO FORCE_FIRST_PASSWORD_CHANGE;
CREATE ROLE AUTONOMY_EXTRACTION_ROLE;
GRANT SELECT ON SCHEMA "SAPHANADB" TO AUTONOMY_EXTRACTION_ROLE;
GRANT AUTONOMY_EXTRACTION_ROLE TO AUTONOMY_EXTRACT;
```

### Security Considerations

| Risk | Mitigation |
|------|------------|
| Direct DB access bypasses ABAP authority checks | Use SELECT-only grants; never grant INSERT/UPDATE/DELETE |
| No client (MANDT) filtering at DB level | Add `WHERE MANDT = '100'` in all queries from Autonomy |
| Exposes all table data including sensitive fields | Grant on individual tables, not entire schema, in production |
| Network exposure on port 30215 | Restrict IP access via AWS Security Group / firewall to Autonomy server only |
| Credential theft | Use certificate-based authentication (HANA supports X.509) |
| Audit trail | Enable HANA audit policies for SELECT on sensitive tables |
| Data at rest | HANA persistence encryption should be enabled |

### HANA Audit Policy (Recommended)

```sql
-- Create audit policy for extraction user activity
CREATE AUDIT POLICY AUTONOMY_EXTRACT_AUDIT
  AUDITING ALL
  ACTIONS SELECT
  FOR AUTONOMY_EXTRACT
  LEVEL INFO
  TRAIL TYPE TABLE;

ALTER AUDIT POLICY AUTONOMY_EXTRACT_AUDIT ENABLE;
```

### Connection Parameters

| Parameter | Value (FAA) |
|-----------|-------------|
| Host | `<ABAP_EXTERNAL_IP>` (from CAL Info tab) |
| Port | `30215` (HANA indexserver, instance 02) |
| Schema | `SAPHANADB` |
| User | `AUTONOMY_EXTRACT` |
| Encrypt | `true` (TLS) |
| SSL Validate Certificate | `false` (self-signed in FAA) |

### Password Policy

| Parameter | Value | Description |
|-----------|-------|-------------|
| `password_layout` | Custom | `A1a!` pattern (upper + lower + digit + special) |
| `minimal_password_length` | 8 | Minimum characters |
| `password_lifetime` | 180 | Days before expiry (0 = never for service accounts) |
| `maximum_invalid_connect_attempts` | 5 | Lock after N failures |
| `password_lock_time` | 1440 | Lock duration in minutes (1440 = 24 hours) |

Set via:
```sql
ALTER USER AUTONOMY_EXTRACT SET PARAMETER PASSWORD_LIFETIME = '0';
ALTER USER AUTONOMY_EXTRACT SET PARAMETER MAXIMUM_INVALID_CONNECT_ATTEMPTS = '5';
```

---

## 4. CSV Export

### Overview

Manual data export from SAP by a customer user. The user extracts table data to CSV/XLSX files via SAP GUI, then uploads to the Autonomy platform. No direct system-to-system connection required.

### Required tCodes

| tCode | Name | Purpose | Authorization Object |
|-------|------|---------|---------------------|
| `SE16` | Data Browser | Display table contents, export to file | `S_TABU_DIS` or `S_TABU_NAM` |
| `SE16N` | General Table Display | Enhanced table display with ALV export | `S_TABU_DIS` or `S_TABU_NAM` |
| `SE16H` | General Table Display (HANA) | HANA-optimized table display | `S_TABU_DIS` or `S_TABU_NAM` |
| `SQVI` | QuickViewer | Multi-table join queries, export | `S_QUERY` + table access |
| `SM30` | Table Maintenance | View/maintain customizing tables | `S_TABU_DIS` (more restrictive) |
| `SA38` / `SE38` | ABAP Program Execution | Run custom extraction reports | `S_PROGRAM` |

### Authorization Objects for Table Display

#### S_TABU_DIS (by Group) or S_TABU_NAM (by Name)

Same objects as RFC (Section 1.2 and 1.3), but used by the SE16/SE16N transaction.

| Object | Field | Value | Purpose |
|--------|-------|-------|---------|
| `S_TABU_DIS` | `ACTVT` = `03`, `DICBERCLS` = relevant groups | Table group display | Broad access by group |
| `S_TABU_NAM` | `ACTVT` = `03`, `TABLE` = specific tables | Named table display | Granular per-table access |

#### S_TCODE — Transaction Code Authorization

| Field | Value |
|-------|-------|
| `TCD` | `SE16`, `SE16N`, `SE16H`, `SQVI` |

### Export Methods

#### Method 1: SE16N ALV Export (Interactive, Recommended)

1. Open SE16N > Enter table name (e.g., `MARA`)
2. Set selection criteria (e.g., `MTART = 'FERT'` for finished goods)
3. Execute query
4. In ALV results: Menu > Spreadsheet (Ctrl+Shift+F7) > Save as CSV
5. Or: Menu > List > Export > Local File > choose "Unconverted" for CSV

**Limitations**: SE16N caps output at 500 rows by default. Change via Settings > User Parameters > `SE16N_MAX_LINES` (set to 999999 for full export). Some systems restrict this.

#### Method 2: SAP GUI Scripting (Automated)

SAP GUI Scripting can automate the SE16 export process. A VBScript macro iterates over a list of tables and exports each to CSV.

**Prerequisites**:
- SAP GUI Scripting enabled on server: profile parameter `sapgui/user_scripting = TRUE`
- SAP GUI Scripting enabled on client: SAP GUI Options > Accessibility & Scripting > Enable scripting
- Authorization: No additional auth objects beyond SE16 table access

**Basic script pattern** (VBScript):
```vbscript
' Opens SE16, enters table name, executes, and exports to CSV
session.findById("wnd[0]/tbar[0]/okcd").text = "/nSE16"
session.findById("wnd[0]").sendVKey 0
session.findById("wnd[0]/usr/ctxtDATABROWSE-TABLENAME").text = "MARA"
session.findById("wnd[0]").sendVKey 0
' ... set selection criteria, execute, export
```

> **SAP Community reference**: "Tip: Write each table with SAP GUI Scripting to a CSV file" — provides a complete working script.

#### Method 3: SQVI Multi-Table Query

1. Open SQVI > Create new query
2. Select base table (e.g., `MARA`)
3. Add joined tables (e.g., `MARC`, `MAKT`)
4. Define join conditions and output fields
5. Execute and export via ALV

**Advantage**: Extracts denormalized data (multiple tables in one file).
**Limitation**: SQVI queries are user-specific (not transportable without conversion to SQ01/SQ02).

#### Method 4: Background Job with SM36/SM37 (Batch)

For large tables, schedule a background job:

1. Create an ABAP report (e.g., `ZEXTRACT_FOR_AUTONOMY`) that reads tables and writes to server file
2. Schedule via SM36
3. Download output file from application server via `CG3Y` (download from app server)

**Authorization objects needed**:
- `S_BTCH_JOB` (background job scheduling)
- `S_DATASET` (file system access)
- `S_PROGRAM` (ABAP program execution)
- Table access objects (S_TABU_DIS/S_TABU_NAM)

### User Creation Steps

1. tCode `SU01` > Create user `ZCSV_AUTONOMY`
2. User Type: **Dialog** (A) — interactive SAP GUI access required
3. Assign role `ZCSV_AUTONOMY_EXPORT` (custom role with SE16N + table access)
4. Set initial password (user must change on first logon)

### Recommended Role

```
Role Name:     ZCSV_AUTONOMY_EXPORT
Description:   Autonomy Platform - CSV Export User
Menu:          SE16N, SE16H, SQVI
Authorization Objects:
  S_TCODE:      TCD = SE16N;SE16H;SQVI
  S_TABU_NAM:   ACTVT=03, TABLE=<all Autonomy tables>
  S_TABU_DIS:   ACTVT=03, DICBERCLS=SC;ME;SD;PP;PM;BC;MM;LF;QM;&NC&
```

### Password Policy

Standard dialog user policy applies:
- Initial password must be changed on first logon
- Password expires per system profile (default 90 days)
- Lockout after 5 failed attempts

---

## 5. FAA User Management

### Unlocking Demo Users in FAA

The SAP S/4HANA 2025 Fully-Activated Appliance ships with demo users **locked by default**.

#### Default Demo Users (Client 100)

| User | Password | Purpose |
|------|----------|---------|
| `S4H_SD_DEM` | `Welcome1` | Sales & Distribution demos |
| `S4H_MM_DEM` | `Welcome1` | Materials Management / Purchasing demos |
| `S4H_PP_DEM` | `Welcome1` | Production Planning demos |
| `S4H_EWM_DEM` | `Welcome1` | Extended Warehouse Management demos |
| `S4H_PM_DEM` | `Welcome1` | Plant Maintenance / Quality demos |
| `BPINST` | `Welcome1` | RFC connections (used in SM59 destinations) |

#### Unlock Procedure

1. Log into SAP GUI using one of:
   - User `DDIC`, Client `000`, Password = Master Password
   - User `SAP*`, Client `000`, Password = Master Password
2. Switch to client `100` via `/nSU01` (or log in directly to client 100)
3. Enter the username (e.g., `BPINST`) > Display
4. Go to menu: User > Unlock
5. Save

**Mass unlock via SU10:**
1. tCode `SU10` > Enter usernames or use selection criteria
2. Select all demo users > Menu: User > Unlock

> **Security warning**: BPINST is used in pre-configured RFC connections (SM59) with a fixed password. If releasing the appliance to multiple users, change the BPINST password and update all SM59 destinations, or create a dedicated RFC user instead.

### Master Password Concept in SAP CAL

The **Master Password** is set during appliance creation in the SAP Cloud Appliance Library console. It is used for:

| System | User | Where Used |
|--------|------|------------|
| Windows RDP VM | `Administrator` | RDP login to Windows Remote Desktop |
| SAP ABAP (Client 000) | `SAP*` | Emergency access to all ABAP clients |
| SAP ABAP (Client 000) | `DDIC` | Data Dictionary / admin access |
| SAP HANA DB | `SYSTEM` | HANA database superuser |
| SAP NetWeaver AS Java | `Administrator` | Java stack admin (NWA) |
| Linux OS (S/4HANA VM) | `root` | SSH access to the ABAP+HANA VM |

**Important characteristics:**
- SAP CAL does **not** store the master password — if forgotten, it cannot be retrieved
- The master password must meet SAP complexity requirements: minimum 8 characters, uppercase, lowercase, digit, special character
- The HANA SYSTEM user password is the master password
- All SAP* / DDIC passwords across all clients are set to the master password

**How to reset if forgotten:**
- **Windows VM**: AWS EC2 console > "Get Windows Password" (requires key pair)
- **HANA SYSTEM user**: SSH to VM as root, use `hdbsql` or `hdbuserstore` to reset
- **SAP* / DDIC**: If you have HANA access, reset via DBACOCKPIT or directly in USR02 table
- **Preventive**: Record the master password in a password manager immediately after appliance creation

---

## 6. Creating a Dedicated Extraction User

### Recommended Pattern: ZRFC_AUTONOMY

#### Step-by-Step (tCode SU01, Client 100)

1. **Login**: SAP GUI > Client 100 > User with user admin rights (DDIC or a user with SAP_ALL in FAA)

2. **Create User**:
   ```
   tCode: SU01
   User:  ZRFC_AUTONOMY
   ```

3. **Address Tab**:
   | Field | Value |
   |-------|-------|
   | Last Name | `Autonomy` |
   | First Name | `RFC Service` |
   | Department | `IT Integration` |
   | E-Mail | `sap-integration@<company>.com` |

4. **Logon Data Tab**:
   | Field | Value |
   |-------|-------|
   | User Type | `Communication` (C) |
   | Initial Password | `<strong_password>` |
   | Time Zone | UTC |
   | Language | EN |

5. **Defaults Tab**:
   | Field | Value |
   |-------|-------|
   | Logon Language | EN |
   | Date Format | YYYY-MM-DD |
   | Decimal Notation | 1,234,567.89 |

6. **Roles Tab**:
   - Add: `ZRFC_AUTONOMY_READ` (custom role from Section 1)

7. **Save**

#### Create the Role (tCode PFCG)

```
tCode: PFCG
Role:  ZRFC_AUTONOMY_READ
Type:  Single Role
```

1. **Description**: "Autonomy Platform — Read-Only RFC Data Extraction"

2. **Authorizations Tab** > Change Authorization Data:

   Add these authorization objects manually:

   ```
   S_RFC
     RFC_TYPE  = FUGR
     RFC_NAME  = SDTX, SYST, SDIFRUNTIME, RFC1, SRFC
     ACTVT     = 16

   S_TABU_NAM
     TABLE     = MARA, MAKT, MARC, MARD, T001W, T001, T001L,
                 STPO, STKO, MAST, EINA, EINE, EORD,
                 LFA1, KNA1, KNVV, CRHD,
                 VBAK, VBAP, EKKO, EKPO, EKET,
                 AFKO, AFPO, LIKP, LIPS,
                 EKBE, MSEG, MKPF, AFRU, AFVC,
                 QALS, KONV, PBIM, PBED,
                 DD02V, DD03L, DD04T, DD17S, DD27S, ENLFDIR
     ACTVT     = 03

   S_TABU_DIS
     DICBERCLS = SC, ME, SD, PP, PM, BC, MM, LF, QM, &NC&
     ACTVT     = 03
   ```

3. **Generate Profile** > Save

#### Verify Authorization

```
tCode: SU53
```

After attempting an RFC call, check SU53 for the last authorization failure. This shows exactly which object/field/value was missing.

Alternatively, use tCode `STAUTHTRACE` (authorization trace) to record all checks during an extraction session.

---

## 7. Security Best Practices

### Principle of Least Privilege

| Principle | Implementation |
|-----------|---------------|
| Read-only access | ACTVT = 03 (Display) only; never 01/02/06 |
| Named table access | Use S_TABU_NAM over S_TABU_DIS where possible |
| No SAP_ALL | Never assign SAP_ALL to integration users |
| Communication user type | Prevents dialog logon via SAP GUI |
| IP restrictions | AWS Security Group limits source IP for ports 3300, 30215, 44301 |
| Credential rotation | Password expiry of 180 days for Communication users |
| Audit logging | Enable SAP Security Audit Log (SM19/SM20) and HANA audit policies |
| Separate users per method | Different users for RFC, OData, HANA — limits blast radius |
| No shared passwords | Each connection type gets its own user with unique credentials |

### Audit Logging

#### ABAP Security Audit Log

```
tCode: SM19  (Configure)
tCode: SM20  (Display)
```

Enable logging for:
- RFC logon events (successful + failed)
- Table access via RFC_READ_TABLE
- Transaction start events

#### HANA Audit Policies

See Section 3 for HANA audit policy SQL.

### Network Security

| Port | Protocol | Source Restriction |
|------|----------|-------------------|
| 3300 | RFC | Autonomy server IP only |
| 30215 | HANA SQL | Autonomy server IP only |
| 44301 | HTTPS (OData/Fiori) | Autonomy server IP + admin IPs |
| 3200 | SAP GUI | Admin workstation IPs only |
| 3389 | RDP | Admin workstation IPs only |

### SAP Note References

| SAP Note | Title | Relevance |
|----------|-------|-----------|
| 460089 | Minimum authorization profile for external RFC programs | RFC user authorization baseline |
| 2aborting | RFC_READ_TABLE security risks and alternatives | Security hardening for RFC table access |
| 1aborting | S_TABU_NAM check before S_TABU_DIS from BASIS 7.50 | Authorization check order change |
| 2373519 | How to GRANT SELECT on schema _SYS_REPO and _SYS_BIC | HANA schema privilege grants |
| 3502308 | Deprecation of API_PURCHASEORDER_PROCESS_SRV | OData V2 API deprecation notice |

> **Note**: Full SAP Note content requires SAP Service Marketplace login (service.sap.com). Note numbers above are references — verify exact note numbers in your S-user portal.

---

## 8. Quick Reference Matrix

### Authorization by Connection Type

| Authorization Object | RFC | OData | HANA Direct | CSV Export |
|---------------------|-----|-------|-------------|-----------|
| S_RFC | Required | - | - | - |
| S_TABU_DIS | Required | - | - | Required |
| S_TABU_NAM | Required (preferred) | - | - | Required (preferred) |
| S_TABU_CLI | If needed | - | - | If needed |
| S_SERVICE | - | Required | - | - |
| IWSV / IWSG | - | Required | - | - |
| S_TCODE | - | - | - | Required |
| HANA SELECT | - | - | Required | - |
| HANA CATALOG READ | - | - | Optional | - |

### User Type by Connection Type

| Connection | Recommended User Type | SAP User | HANA User |
|------------|----------------------|----------|-----------|
| RFC | Communication (C) | `ZRFC_AUTONOMY` | - |
| OData | Service (S) | `ZODATA_AUTONOMY` | - |
| HANA Direct | - | - | `AUTONOMY_EXTRACT` |
| CSV Export | Dialog (A) | `ZCSV_AUTONOMY` | - |

### Port and Protocol Summary

| Connection | Port | Protocol | Encryption |
|------------|------|----------|------------|
| RFC | 3300 | SAP RFC protocol | SNC optional |
| OData | 44301 | HTTPS | TLS required |
| HANA Direct | 30215 | HANA SQL protocol | TLS required |
| CSV Export | 3200 (SAP GUI) | DIAG protocol | SNC optional |

### Effort Comparison

| Aspect | RFC | OData | HANA Direct | CSV Export |
|--------|-----|-------|-------------|-----------|
| Setup complexity | Medium | High (service activation) | Low (SQL only) | Low (manual) |
| Ongoing effort | None (automated) | None (automated) | None (automated) | High (manual per extract) |
| Security risk | Low-Medium | Low | High (direct DB) | Very Low |
| Speed | Fast | Medium (HTTP overhead) | Fastest | Slowest |
| Table coverage | All ABAP tables | Only published APIs | All DB tables | All displayable tables |
| ABAP auth checks | Yes (S_TABU_*) | Yes (full stack) | NO (bypassed) | Yes (S_TABU_*) |
| Recommended for | Production extraction | Modern S/4HANA | Bulk historical data | Initial setup / fallback |

---

## References

### SAP Documentation
- [SAP Note 460089 — Minimum authorization for external RFC](https://www.stechno.net/repository/sap-notes.html?id=460089)
- [Authorization Objects S_TABU_DIS, S_TABU_NAM](https://help.sap.com/docs/SAP_Solution_Manager/fd3c83ed48684640a18ac05c8ae4d016/e50e0edcd9c54144b5b614c4ba27204d.html)
- [SAP HANA GRANT Statement](https://help.sap.com/docs/SAP_HANA_PLATFORM/4fe29514fd584807ac9f2a04f6754767/20f674e1751910148a8b990d33efbdc5.html)
- [SAP HANA Privileges and Roles](https://learning.sap.com/learning-journeys/installing-and-administering-sap-hana/describing-sap-hana-privileges-and-roles)
- [S/4HANA 2025 FAA Known Issues](https://community.sap.com/t5/technology-blog-posts-by-sap/sap-s-4hana-2025-fully-activated-appliance-known-issues/ba-p/14260301)
- [SAP CAL Master Password](https://help.sap.com/docs/PRODUCT_ID/041a179a4a1244808927cd6816bf8bb7/826a39d7d67d48ec90ab2fa516f3df4c.html)

### Third-Party References
- [Theobald Software — SAP Authorization Objects](https://helpcenter.theobald-software.com/xtract-is/documentation/setup-in-sap/sap-authority-objects/)
- [Theobald Knowledge Base — SAP User Rights](https://kb.theobald-software.com/sap/authority-objects-sap-user-rights)
- [rfcconnector.com — Minimum ABAP Permissions](https://rfcconnector.com/documentation/kb/0015/)
- [Panaya — RFC User Authorizations](https://success.panaya.com/docs/rfc-authorizations)
- [Onapsis — RFC_READ_TABLE Security](https://onapsis.com/blog/sap-rfc-read-table-accessing-arbitrary-tables/)
- [Pathlock — SAP Fiori Authorization](https://pathlock.com/configuring-and-assigning-sap-authorizations-in-sap-fiori-apps/)
- [S_TABU_NAM and S_TABU_DIS explained (Aglea)](https://www.aglea.com/en/blog/s_tabu_nam-s_tabu_dis-in-sap)
- [SAP Community — Authorization Objects for S/4 HANA RFC User](https://community.sap.com/t5/enterprise-resource-planning-q-a/authorization-objects-for-s-4-hana-rfc-user/qaq-p/716776)
- [HANA Grant SELECT on schema](https://community.sap.com/t5/technology-q-a/how-can-i-grant-select-any-table-in-any-schema-to-user-in-hana-database/qaq-p/12396567)
- [Grant Read Only Access in HANA](https://community.sap.com/t5/technology-q-a/grant-read-only-access-to-a-user-in-hana-database/qaq-p/12516448)
- [SAP GUI Scripting CSV Export](https://community.sap.com/t5/technology-blog-posts-by-members/tip-write-each-table-with-sap-gui-scripting-to-a-csv-file/ba-p/13210301)
- [SE16N Data Export formats](https://www.dab-europe.com/en/articles/formats-for-download-from-sap-se16/)
- [dbosoft — SAP User Types](https://dbosoft.eu/en-us/blog/using-sap-user-types-correctly)
- [SAP OData Service Registration](https://gocoding.org/how-to-register-sap-odata-service-iwfnd-maint_service/)
- [SAP Fiori OData Authorization Troubleshooting](https://sii.pl/blog/en/sap-fiori-authorization-troubleshooting/)
