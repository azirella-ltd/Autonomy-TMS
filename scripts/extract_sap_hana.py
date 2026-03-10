#!/usr/bin/env python3
"""
SAP S/4HANA IDES Data Extraction — Direct HANA SQL

Extracts ALL master + transactional data directly from HANA DB.
OData services aren't activated on this FAA, so we go direct.

Usage:
    python scripts/extract_sap_hana.py --password <MASTER_PASSWORD>
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from hdbcli import dbapi

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "imports" / "SAP" / "IDES_1710"
SCHEMA = "SAPHANADB"

# Plant filter: VKORG = '1710' gets Plant 1710 (Palo Alto) and 1720
# We use a subselect pattern for consistency
PLANT_FILTER = f"WERKS IN (SELECT WERKS FROM {SCHEMA}.T001W WHERE VKORG = '1710')"
COMPANY_FILTER = "BUKRS = '1710'"
SALES_ORG_FILTER = "VKORG = '1710'"


# ============================================================================
# Extraction Queries
# ============================================================================

EXTRACTIONS: Dict[str, List[Dict[str, str]]] = {

    "master": [
        {
            "name": "Company Codes",
            "filename": "T001_company_codes.csv",
            "query": f"SELECT BUKRS, BUTXT, LAND1, WAERS, SPRAS FROM {SCHEMA}.T001 WHERE {COMPANY_FILTER}",
        },
        {
            "name": "Plants / Sites",
            "filename": "T001W_plants.csv",
            "query": f"""
                SELECT WERKS, NAME1, BWKEY, VKORG, EKORG, FABKL,
                       STRAS, ORT01, PSTLZ, REGIO, LAND1, ADRNR
                FROM {SCHEMA}.T001W
                WHERE {SALES_ORG_FILTER}
                ORDER BY WERKS
            """,
        },
        {
            "name": "Storage Locations",
            "filename": "T001L_storage_locations.csv",
            "query": f"""
                SELECT WERKS, LGORT, LGOBE
                FROM {SCHEMA}.T001L
                WHERE {PLANT_FILTER}
                ORDER BY WERKS, LGORT
            """,
        },
        {
            "name": "Materials (General)",
            "filename": "MARA_materials.csv",
            "query": f"""
                SELECT m.MATNR, m.MTART, m.MEINS, m.MATKL, m.BRGEW, m.NTGEW,
                       m.GEWEI, m.VOLUM, m.VOLEH, m.MBRSH, m.ERSDA, m.LAEDA,
                       m.EAN11, m.NUMTP, m.PRDHA
                FROM {SCHEMA}.MARA m
                WHERE EXISTS (
                    SELECT 1 FROM {SCHEMA}.MARC mc
                    WHERE mc.MATNR = m.MATNR AND mc.{PLANT_FILTER}
                )
                ORDER BY m.MATNR
            """,
        },
        {
            "name": "Material Descriptions",
            "filename": "MAKT_descriptions.csv",
            "query": f"""
                SELECT t.MATNR, t.SPRAS, t.MAKTX
                FROM {SCHEMA}.MAKT t
                WHERE t.SPRAS = 'E'
                AND EXISTS (
                    SELECT 1 FROM {SCHEMA}.MARC mc
                    WHERE mc.MATNR = t.MATNR AND mc.{PLANT_FILTER}
                )
                ORDER BY t.MATNR
            """,
        },
        {
            "name": "Material-Plant (MRP, Procurement)",
            "filename": "MARC_material_plant.csv",
            "query": f"""
                SELECT MATNR, WERKS, EKGRP, DISMM, DISPO, DISLS,
                       MINBE, EISBE, BSTRF, BSTMI, BSTMA,
                       BESKZ, SOBSL, PLIFZ, WEBAZ, FHORI,
                       MABST, LOSGR, FXHOR, VRMOD, VINT1, VINT2,
                       STRGR, LGPRO, LGFSB, PRCTR
                FROM {SCHEMA}.MARC
                WHERE {PLANT_FILTER}
                ORDER BY MATNR, WERKS
            """,
        },
        {
            "name": "Material Valuation (Unit Costs)",
            "filename": "MBEW_valuation.csv",
            "query": f"""
                SELECT MATNR, BWKEY, BKLAS, VPRSV, VERPR, STPRS,
                       PEINH, SALK3, LBKUM
                FROM {SCHEMA}.MBEW
                WHERE BWKEY IN (SELECT WERKS FROM {SCHEMA}.T001W WHERE {SALES_ORG_FILTER})
                ORDER BY MATNR, BWKEY
            """,
        },
        {
            "name": "Material Sales Data",
            "filename": "MVKE_sales_data.csv",
            "query": f"""
                SELECT MATNR, VKORG, VTWEG, PRODH, KONDM, KTGRM, MTPOS
                FROM {SCHEMA}.MVKE
                WHERE {SALES_ORG_FILTER}
                ORDER BY MATNR, VKORG, VTWEG
            """,
        },
        {
            "name": "UOM Conversions",
            "filename": "MARM_uom_conversions.csv",
            "query": f"""
                SELECT m.MATNR, m.MEINH, m.UMREZ, m.UMREN, m.BRGEW, m.VOLUM
                FROM {SCHEMA}.MARM m
                WHERE EXISTS (
                    SELECT 1 FROM {SCHEMA}.MARC mc
                    WHERE mc.MATNR = m.MATNR AND mc.{PLANT_FILTER}
                )
                ORDER BY m.MATNR, m.MEINH
            """,
        },
        {
            "name": "BOM Headers",
            "filename": "STKO_bom_headers.csv",
            "query": f"""
                SELECT STLNR, STLAL, STLTY, STLST, BMENG,
                       BMEIN, STKTX, DATUV, LOEKZ
                FROM {SCHEMA}.STKO
                WHERE STLTY = 'M'
                ORDER BY STLNR, STLAL
            """,
        },
        {
            "name": "BOM Items",
            "filename": "STPO_bom_items.csv",
            "query": f"""
                SELECT i.STLNR, i.STLKN, i.STPOZ, i.IDNRK, i.MENGE,
                       i.MEINS, i.POSTP, i.POSNR, i.SORTF, i.AUSCH
                FROM {SCHEMA}.STPO i
                WHERE EXISTS (
                    SELECT 1 FROM {SCHEMA}.STKO h
                    WHERE h.STLNR = i.STLNR AND h.STLTY = 'M'
                )
                ORDER BY i.STLNR, i.STLKN
            """,
        },
        {
            "name": "Vendors / Suppliers",
            "filename": "LFA1_vendors.csv",
            "query": f"""
                SELECT LIFNR, NAME1, NAME2, LAND1, REGIO, ORT01,
                       PSTLZ, STRAS, TELF1, ADRNR
                FROM {SCHEMA}.LFA1
                ORDER BY LIFNR
            """,
        },
        {
            "name": "Customers",
            "filename": "KNA1_customers.csv",
            "query": f"""
                SELECT KUNNR, NAME1, NAME2, LAND1, REGIO, ORT01,
                       PSTLZ, STRAS, TELF1, ADRNR, KTOKD
                FROM {SCHEMA}.KNA1
                ORDER BY KUNNR
            """,
        },
        {
            "name": "Addresses",
            "filename": "ADRC_addresses.csv",
            "query": f"""
                SELECT ADDRNUMBER, NAME1, CITY1, POST_CODE1,
                       REGION, COUNTRY, STREET, HOUSE_NUM1,
                       TEL_NUMBER, FAX_NUMBER
                FROM {SCHEMA}.ADRC
                WHERE COUNTRY IN ('US', 'DE', 'GB', 'JP', 'CN')
                ORDER BY ADDRNUMBER
            """,
        },
        {
            "name": "Work Centers",
            "filename": "CRHD_work_centers.csv",
            "query": f"""
                SELECT OBJID, ARBPL, WERKS, VERWE, OBJTY
                FROM {SCHEMA}.CRHD
                WHERE {PLANT_FILTER}
                ORDER BY WERKS, ARBPL
            """,
        },
    ],

    "sourcing": [
        {
            "name": "Purchasing Info Records (General)",
            "filename": "EINA_purchasing_info_general.csv",
            "query": f"""
                SELECT INFNR, MATNR, LIFNR, LOEKZ, ERDAT, TXZ01, MEINS
                FROM {SCHEMA}.EINA
                ORDER BY INFNR
            """,
        },
        {
            "name": "Purchasing Info Records (Org-Level)",
            "filename": "EINE_purchasing_info_org.csv",
            "query": f"""
                SELECT INFNR, EKORG, WERKS, ESOKZ,
                       NETPR, PEINH, WAERS, APLFZ,
                       NORBM, MINBM, UEBTO, UNTTO
                FROM {SCHEMA}.EINE
                WHERE EKORG = '1710'
                   OR {PLANT_FILTER}
                ORDER BY INFNR, EKORG
            """,
        },
        {
            "name": "Source List",
            "filename": "EORD_source_list.csv",
            "query": f"""
                SELECT MATNR, WERKS, ZEORD, VDATU, BDATU,
                       LIFNR, FLIFN, NOTKZ, EKORG, EORTP
                FROM {SCHEMA}.EORD
                WHERE {PLANT_FILTER}
                ORDER BY MATNR, WERKS
            """,
        },
    ],

    "demand": [
        {
            "name": "Sales Order Headers",
            "filename": "VBAK_sales_orders.csv",
            "query": f"""
                SELECT VBELN, AUART, VKORG, VTWEG, SPART,
                       KUNNR, ERDAT, VDATU, BSTNK, WAERK,
                       NETWR, KNUMV, GBSTK
                FROM {SCHEMA}.VBAK
                WHERE {SALES_ORG_FILTER}
                ORDER BY VBELN
            """,
        },
        {
            "name": "Sales Order Items",
            "filename": "VBAP_sales_order_items.csv",
            "query": f"""
                SELECT p.VBELN, p.POSNR, p.MATNR, p.WERKS,
                       p.KWMENG, p.MEINS, p.NETPR, p.NETWR,
                       p.WAERK, p.LFREL, p.ABGRU, p.PSTYV
                FROM {SCHEMA}.VBAP p
                WHERE EXISTS (
                    SELECT 1 FROM {SCHEMA}.VBAK h
                    WHERE h.VBELN = p.VBELN AND h.{SALES_ORG_FILTER}
                )
                ORDER BY p.VBELN, p.POSNR
            """,
        },
        {
            "name": "Sales Order Schedule Lines",
            "filename": "VBEP_schedule_lines.csv",
            "query": f"""
                SELECT s.VBELN, s.POSNR, s.ETENR, s.EDATU,
                       s.WMENG, s.BMENG, s.LMENG, s.MEINS
                FROM {SCHEMA}.VBEP s
                WHERE EXISTS (
                    SELECT 1 FROM {SCHEMA}.VBAK h
                    WHERE h.VBELN = s.VBELN AND h.{SALES_ORG_FILTER}
                )
                ORDER BY s.VBELN, s.POSNR, s.ETENR
            """,
        },
    ],

    "procurement": [
        {
            "name": "Purchase Order Headers",
            "filename": "EKKO_purchase_orders.csv",
            "query": f"""
                SELECT EBELN, BSART, BSTYP, LIFNR, EKORG, EKGRP,
                       BUKRS, ERNAM, AEDAT, BEDAT, WAERS
                FROM {SCHEMA}.EKKO
                WHERE {COMPANY_FILTER}
                ORDER BY EBELN
            """,
        },
        {
            "name": "Purchase Order Items",
            "filename": "EKPO_purchase_order_items.csv",
            "query": f"""
                SELECT p.EBELN, p.EBELP, p.MATNR, p.WERKS, p.LGORT,
                       p.MENGE, p.MEINS, p.NETPR, p.PEINH, p.NETWR,
                       p.BPRME, p.BSTYP, p.KNTTP, p.PSTYP, p.ELIKZ
                FROM {SCHEMA}.EKPO p
                WHERE EXISTS (
                    SELECT 1 FROM {SCHEMA}.EKKO h
                    WHERE h.EBELN = p.EBELN AND h.{COMPANY_FILTER}
                )
                ORDER BY p.EBELN, p.EBELP
            """,
        },
        {
            "name": "PO Schedule Lines",
            "filename": "EKET_po_schedule_lines.csv",
            "query": f"""
                SELECT s.EBELN, s.EBELP, s.ETENR, s.EINDT,
                       s.MENGE, s.WEMNG, s.WAMNG, s.SLFDT
                FROM {SCHEMA}.EKET s
                WHERE EXISTS (
                    SELECT 1 FROM {SCHEMA}.EKKO h
                    WHERE h.EBELN = s.EBELN AND h.{COMPANY_FILTER}
                )
                ORDER BY s.EBELN, s.EBELP, s.ETENR
            """,
        },
        {
            "name": "Purchase Requisitions",
            "filename": "EBAN_purchase_requisitions.csv",
            "query": f"""
                SELECT BANFN, BNFPO, BSART, MATNR, WERKS, LGORT,
                       MENGE, MEINS, PREIS, PEINH, EKGRP,
                       FRGKZ, FRGZU, LOEKZ, BADAT, LFDAT
                FROM {SCHEMA}.EBAN
                WHERE {PLANT_FILTER}
                ORDER BY BANFN, BNFPO
            """,
        },
    ],

    "manufacturing": [
        {
            "name": "Production Order Headers",
            "filename": "AFKO_production_orders.csv",
            "query": f"""
                SELECT k.AUFNR, k.RSNUM, k.PLNBEZ, k.GAMNG, k.GMEIN,
                       k.GSTRS, k.GSTRP, k.FTRMS, k.GLTRP,
                       k.GLTRS, k.PLNTY, k.PLNNR
                FROM {SCHEMA}.AFKO k
                WHERE EXISTS (
                    SELECT 1 FROM {SCHEMA}.AUFK a
                    WHERE a.AUFNR = k.AUFNR AND a.{PLANT_FILTER}
                )
                ORDER BY k.AUFNR
            """,
        },
        {
            "name": "Production Order Items",
            "filename": "AFPO_production_order_items.csv",
            "query": f"""
                SELECT p.AUFNR, p.POSNR, p.MATNR, p.MEINS,
                       p.PSMNG, p.WEMNG, p.LTRMI, p.LTRMP
                FROM {SCHEMA}.AFPO p
                WHERE EXISTS (
                    SELECT 1 FROM {SCHEMA}.AUFK a
                    WHERE a.AUFNR = p.AUFNR AND a.{PLANT_FILTER}
                )
                ORDER BY p.AUFNR, p.POSNR
            """,
        },
        {
            "name": "Planned Orders (MRP Output)",
            "filename": "PLAF_planned_orders.csv",
            "query": f"""
                SELECT PLNUM, MATNR, PLWRK, GSMNG, MEINS,
                       PEDTR, PSTTR, STLFX, PAART, BESKZ,
                       PLNTY, DISPO
                FROM {SCHEMA}.PLAF
                WHERE PLWRK IN (SELECT WERKS FROM {SCHEMA}.T001W WHERE {SALES_ORG_FILTER})
                ORDER BY PLNUM
            """,
        },
        {
            "name": "Routing Headers",
            "filename": "PLKO_routing_headers.csv",
            "query": f"""
                SELECT PLNTY, PLNNR, PLNAL, WERKS, STATU,
                       LOEKZ, PLNME, VERWE, KTEXT
                FROM {SCHEMA}.PLKO
                WHERE WERKS IN (SELECT WERKS FROM {SCHEMA}.T001W WHERE {SALES_ORG_FILTER})
                ORDER BY PLNTY, PLNNR, PLNAL
            """,
        },
        {
            "name": "Routing Operations",
            "filename": "PLPO_routing_operations.csv",
            "query": f"""
                SELECT o.PLNTY, o.PLNNR, o.PLNKN, o.VORNR,
                       o.ARBID, o.STEUS, o.VGW01, o.VGW02, o.VGW03,
                       o.VGE01, o.VGE02, o.VGE03, o.BMSCH
                FROM {SCHEMA}.PLPO o
                WHERE EXISTS (
                    SELECT 1 FROM {SCHEMA}.PLKO h
                    WHERE h.PLNTY = o.PLNTY AND h.PLNNR = o.PLNNR
                    AND h.WERKS IN (SELECT WERKS FROM {SCHEMA}.T001W WHERE {SALES_ORG_FILTER})
                )
                ORDER BY o.PLNTY, o.PLNNR, o.PLNKN
            """,
        },
        {
            "name": "Component Reservations (MO)",
            "filename": "RESB_reservations.csv",
            "query": f"""
                SELECT RSNUM, RSPOS, MATNR, WERKS, LGORT,
                       BDMNG, MEINS, BDTER, AUFNR, XWAOK, ENMNG
                FROM {SCHEMA}.RESB
                WHERE {PLANT_FILTER}
                ORDER BY RSNUM, RSPOS
            """,
        },
    ],

    "distribution": [
        {
            "name": "Delivery Headers",
            "filename": "LIKP_deliveries.csv",
            "query": f"""
                SELECT VBELN, LFART, WADAT, WADAT_IST, LDDAT,
                       LFDAT, ROUTE, BTGEW, NTGEW, VOLUM,
                       GEWEI, VOLEH, KUNNR, LIFNR, VSTEL, VKORG
                FROM {SCHEMA}.LIKP
                WHERE {SALES_ORG_FILTER}
                ORDER BY VBELN
            """,
        },
        {
            "name": "Delivery Items",
            "filename": "LIPS_delivery_items.csv",
            "query": f"""
                SELECT i.VBELN, i.POSNR, i.MATNR, i.WERKS, i.LGORT,
                       i.LFIMG, i.MEINS, i.VGBEL, i.VGPOS, i.PSTYV
                FROM {SCHEMA}.LIPS i
                WHERE EXISTS (
                    SELECT 1 FROM {SCHEMA}.LIKP h
                    WHERE h.VBELN = i.VBELN AND h.{SALES_ORG_FILTER}
                )
                ORDER BY i.VBELN, i.POSNR
            """,
        },
    ],

    "quality": [
        {
            "name": "Quality/Maint Notifications",
            "filename": "QMEL_notifications.csv",
            "query": f"""
                SELECT QMNUM, QMART, MATNR, ERDAT, PRIOK,
                       STRMN, LTRMN, QMTXT, AUFNR
                FROM {SCHEMA}.QMEL
                WHERE MATNR IN (
                    SELECT MATNR FROM {SCHEMA}.MARC WHERE {PLANT_FILTER}
                )
                ORDER BY QMNUM
            """,
        },
    ],

    "maintenance": [
        {
            "name": "Orders (PP/PM)",
            "filename": "AUFK_orders.csv",
            "query": f"""
                SELECT AUFNR, AUART, AUTYP, WERKS, ERDAT,
                       BUKRS, KTEXT, OBJNR, WAERS
                FROM {SCHEMA}.AUFK
                WHERE {PLANT_FILTER}
                ORDER BY AUFNR
            """,
        },
        {
            "name": "Equipment Master",
            "filename": "EQUI_equipment.csv",
            "query": f"""
                SELECT EQUNR, EQART, ERDAT, ANSDT, ANSWT,
                       WAERS, HERST, SERGE, TYPBZ, BRGEW, GEWEI
                FROM {SCHEMA}.EQUI
                WHERE EQUNR IN (
                    SELECT EQUNR FROM {SCHEMA}.EQUI WHERE EQUNR IS NOT NULL
                )
                ORDER BY EQUNR
            """,
        },
    ],

    "inventory": [
        {
            "name": "Stock by Storage Location",
            "filename": "MARD_stock.csv",
            "query": f"""
                SELECT MATNR, WERKS, LGORT, LABST, UMLME,
                       INSME, EINME, SPEME, RETME
                FROM {SCHEMA}.MARD
                WHERE {PLANT_FILTER}
                ORDER BY MATNR, WERKS, LGORT
            """,
        },
    ],
}


# ============================================================================
# Fuzzy Column Matching — adapts queries to actual S/4HANA version
# ============================================================================

# Cache of table -> set of column names
_table_columns_cache: Dict[str, set] = {}


def get_table_columns(cursor, table_name: str) -> set:
    """Get actual column names for a table from HANA catalog."""
    if table_name in _table_columns_cache:
        return _table_columns_cache[table_name]
    try:
        cursor.execute(
            f"SELECT COLUMN_NAME FROM SYS.TABLE_COLUMNS "
            f"WHERE SCHEMA_NAME='{SCHEMA}' AND TABLE_NAME='{table_name}'"
        )
        cols = {row[0] for row in cursor.fetchall()}
        _table_columns_cache[table_name] = cols
        return cols
    except Exception:
        return set()


def fuzzy_match_column(target: str, available: set) -> str:
    """Find the best fuzzy match for a column name.

    Strategy:
    1. Exact match
    2. Case-insensitive match
    3. Substring match (target contained in available or vice versa)
    4. Levenshtein distance <= 2
    5. Give up — return None
    """
    if target in available:
        return target

    target_upper = target.upper()
    for col in available:
        if col.upper() == target_upper:
            return col

    # Substring: e.g., GMEIN -> find MEINS, GMEING, etc.
    for col in sorted(available):
        if target_upper in col.upper() or col.upper() in target_upper:
            return col

    # Levenshtein distance
    best_col, best_dist = None, 999
    for col in available:
        dist = _levenshtein(target_upper, col.upper())
        if dist < best_dist:
            best_dist = dist
            best_col = col
    if best_dist <= 2:
        return best_col

    return None


def _levenshtein(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


import re

# Pattern to extract table references and column names from SELECT queries
_SELECT_COL_RE = re.compile(
    r"(?:SELECT\s+)(.*?)(?:\s+FROM\s+)", re.IGNORECASE | re.DOTALL
)
_FROM_TABLE_RE = re.compile(
    rf"FROM\s+{re.escape(SCHEMA)}\.(\w+)", re.IGNORECASE
)
_ALIAS_RE = re.compile(r"(\w+)\.(\w+)")


def validate_and_fix_query(cursor, query: str) -> str:
    """Validate all column references in a query against actual HANA catalog.

    For each SELECT column that doesn't exist in the table, find the best
    fuzzy match and rewrite the query. Logs all substitutions.
    """
    # Extract table names from the query
    tables_in_query = _FROM_TABLE_RE.findall(query)
    if not tables_in_query:
        return query

    # Build column sets for all tables
    table_cols: Dict[str, set] = {}
    for tname in tables_in_query:
        table_cols[tname] = get_table_columns(cursor, tname)

    # Find alias -> table mappings (e.g., "k" -> "AFKO")
    alias_map: Dict[str, str] = {}
    # Simple: "FROM SCHEMA.TABLE alias" or "FROM SCHEMA.TABLE"
    alias_pattern = re.compile(
        rf"{re.escape(SCHEMA)}\.(\w+)\s+(\w+)(?:\s|$|,)", re.IGNORECASE
    )
    for match in alias_pattern.finditer(query):
        alias_map[match.group(2).upper()] = match.group(1)
    # Also map unaliased tables
    for tname in tables_in_query:
        alias_map[tname] = tname

    # Primary table is the first FROM
    primary_table = tables_in_query[0]

    replacements = {}
    fixed_query = query

    # Check each "alias.COLUMN" reference
    for match in _ALIAS_RE.finditer(query):
        alias, col = match.group(1).upper(), match.group(2)
        table = alias_map.get(alias)
        if not table or table not in table_cols:
            continue
        if col not in table_cols[table]:
            replacement = fuzzy_match_column(col, table_cols[table])
            if replacement and replacement != col:
                old_ref = f"{match.group(1)}.{col}"
                new_ref = f"{match.group(1)}.{replacement}"
                replacements[old_ref] = new_ref
                logger.info(f"    Column fix: {old_ref} -> {new_ref}")
            elif not replacement:
                logger.warning(f"    Column {alias}.{col} not found in {table}, dropping")

    # Check bare column references (no alias) against primary table
    select_match = _SELECT_COL_RE.search(query)
    if select_match:
        select_clause = select_match.group(1)
        for col_token in re.findall(r"\b([A-Z_][A-Z0-9_]*)\b", select_clause):
            if col_token in ("SELECT", "FROM", "AS", "DISTINCT", SCHEMA):
                continue
            if "." in select_clause and col_token in [m.group(2) for m in _ALIAS_RE.finditer(select_clause)]:
                continue  # Already handled as alias.col
            if col_token not in table_cols.get(primary_table, set()):
                replacement = fuzzy_match_column(col_token, table_cols.get(primary_table, set()))
                if replacement and replacement != col_token:
                    replacements[col_token] = replacement
                    logger.info(f"    Column fix: {col_token} -> {replacement} (in {primary_table})")

    # Apply replacements
    for old, new in replacements.items():
        fixed_query = fixed_query.replace(old, new)

    return fixed_query


# ============================================================================
# Engine
# ============================================================================

def extract_to_csv(cursor, query: str, filepath: Path, auto_fix: bool = True) -> int:
    """Execute query and write results to CSV.

    If auto_fix is True, validates column names against HANA catalog
    and fuzzy-matches any that don't exist.
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)

    if auto_fix:
        query = validate_and_fix_query(cursor, query)

    try:
        cursor.execute(query)
    except Exception as e:
        logger.error(f"  Query failed: {e}")
        with open(filepath, "w") as f:
            f.write(f"# ERROR: {e}\n")
        return -1

    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in rows:
            clean = []
            for val in row:
                if val is None:
                    clean.append("")
                elif isinstance(val, (bytes, memoryview)):
                    clean.append(val.hex() if len(val) > 0 else "")
                elif isinstance(val, datetime):
                    clean.append(val.isoformat())
                else:
                    clean.append(str(val).strip())
            writer.writerow(clean)

    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Extract SAP IDES data via HANA SQL")
    parser.add_argument("--host", default=os.environ.get("SAP_HOST", "63.182.191.72"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SAP_HANA_PORT", "30215")))
    parser.add_argument("--user", default=os.environ.get("SAP_HANA_USER", "SAPHANADB"))
    parser.add_argument("--password", default=os.environ.get("SAP_PASS"))
    parser.add_argument("--categories", nargs="+", choices=list(EXTRACTIONS.keys()), default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.password:
        print("ERROR: Password required. Use --password <PW> or set SAP_PASS env var.")
        sys.exit(1)

    categories = args.categories or list(EXTRACTIONS.keys())

    logger.info("=" * 70)
    logger.info("SAP S/4HANA IDES — HANA Direct SQL Extraction")
    logger.info("=" * 70)
    logger.info(f"Host:       {args.host}:{args.port}")
    logger.info(f"User:       {args.user}, Schema: {SCHEMA}")
    logger.info(f"Categories: {', '.join(categories)}")
    logger.info(f"Output:     {OUTPUT_DIR}")

    conn = dbapi.connect(address=args.host, port=args.port, user=args.user, password=args.password)
    cursor = conn.cursor()
    logger.info("Connected to HANA")

    if args.dry_run:
        cursor.execute("SELECT CURRENT_TIMESTAMP FROM DUMMY")
        logger.info(f"Dry run OK. Server time: {cursor.fetchone()[0]}")
        conn.close()
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {}
    grand_total = 0
    errors = 0

    for category in categories:
        extractions = EXTRACTIONS.get(category, [])
        if not extractions:
            continue

        logger.info(f"\n{'=' * 50}")
        logger.info(f"CATEGORY: {category.upper()}")
        logger.info(f"{'=' * 50}")

        cat_results = {}
        for ext in extractions:
            name = ext["name"]
            filepath = OUTPUT_DIR / ext["filename"]
            logger.info(f"\n  [{name}]")

            t0 = time.time()
            count = extract_to_csv(cursor, ext["query"], filepath)
            elapsed = time.time() - t0

            if count >= 0:
                logger.info(f"  -> {count:,} rows -> {ext['filename']} ({elapsed:.1f}s)")
                grand_total += count
            else:
                errors += 1

            cat_results[name] = {"filename": ext["filename"], "records": max(count, 0), "error": count < 0}

        results[category] = cat_results

    cursor.close()
    conn.close()

    # Manifest
    manifest = {
        "extraction_timestamp": datetime.now().isoformat(),
        "source": "S/4HANA 2025 FAA (IDES) via HANA SQL",
        "schema": SCHEMA, "company_code": "1710", "plant_filter": "VKORG=1710",
        "categories": {cat: {"records": sum(e["records"] for e in exts.values())}
                       for cat, exts in results.items()},
        "total_records": grand_total, "errors": errors,
    }
    with open(OUTPUT_DIR / "MANIFEST.json", "w") as f:
        json.dump(manifest, f, indent=2)

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("EXTRACTION COMPLETE")
    logger.info("=" * 70)

    for category, exts in results.items():
        cat_total = sum(e["records"] for e in exts.values())
        logger.info(f"\n  {category.upper()} ({cat_total:,} rows)")
        for name, info in exts.items():
            icon = "ok" if not info.get("error") and info["records"] > 0 else ("!!" if info.get("error") else "--")
            logger.info(f"    [{icon}] {info['filename']:45s} {info['records']:>8,}")

    logger.info(f"\n  TOTAL: {grand_total:,} records, {errors} errors")
    logger.info(f"  Output: {OUTPUT_DIR}/")

    if errors == 0:
        logger.info("\n  All extractions successful!")
        logger.info("  Next: SUSPEND SAP in CAL, then create CSV connection in Autonomy")


if __name__ == "__main__":
    main()
