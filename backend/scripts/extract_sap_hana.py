#!/usr/bin/env python3
"""
Extract SAP tables directly from HANA database.

Connects to SAP S/4HANA's underlying HANA database and exports
standard tables as CSV files ready for the SAP ingestion pipeline.

Usage:
    # Interactive — prompts for connection details
    python scripts/extract_sap_hana.py

    # With connection parameters
    python scripts/extract_sap_hana.py \
        --host 10.0.0.1 --port 30015 \
        --user SAPHANADB --password Secret123 \
        --company-code 1710

    # Extract only specific tables
    python scripts/extract_sap_hana.py --tables EKKO,EKPO,VBAK,VBAP,LIKP,LIPS

    # Using .env file
    python scripts/extract_sap_hana.py --env-file .env.sap

Environment variables (alternative to CLI args):
    SAP_HANA_HOST, SAP_HANA_PORT, SAP_HANA_USER, SAP_HANA_PASSWORD
    SAP_COMPANY_CODE (default: 1710)

Requirements:
    pip install hdbcli
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SAP Table definitions: table_name → (columns, where_clause_template)
#
# where_clause_template uses {bukrs} for company code, {werks} for plant list
# ---------------------------------------------------------------------------

SAP_TABLES: Dict[str, Tuple[List[str], str]] = {
    # ── Master Data (Phase 1) ──────────────────────────────────────────
    "T001": (
        ["BUKRS", "BUTXT", "WAERS", "LAND1", "SPRAS"],
        "BUKRS = '{bukrs}'",
    ),
    "T001W": (
        ["WERKS", "NAME1", "BWKEY", "BUKRS", "FABKL", "TXJCD", "J_1BBRANCH",
         "STRAS", "PFACH", "PSTLZ", "ORT01", "LAND1", "REGIO", "SPRAS",
         "ADRNR", "IWERK", "EKORG"],
        "BUKRS = '{bukrs}'",
    ),
    "T001L": (
        ["WERKS", "LGORT", "LGOBE", "KOBER"],
        "WERKS IN ({werks})",
    ),
    "ADRC": (
        ["ADDRNUMBER", "NAME1", "CITY1", "CITY2", "REGION", "COUNTRY",
         "POST_CODE1", "STREET", "STR_SUPPL1", "STR_SUPPL2", "BUILDING",
         "TEL_NUMBER", "FAX_NUMBER", "TIME_ZONE"],
        # ADRC has no direct BUKRS filter — we'll join via T001W.ADRNR
        "",
    ),
    "MARA": (
        ["MATNR", "MTART", "MBRSH", "MATKL", "MEINS", "BRGEW", "NTGEW",
         "GEWEI", "VOLUM", "VOLEH", "PRDHA", "SPART", "LVORM", "ERSDA",
         "LAEDA", "EAN11"],
        "",  # Filtered via MARC
    ),
    "MAKT": (
        ["MATNR", "SPRAS", "MAKTX"],
        "SPRAS = 'E'",
    ),
    "MARC": (
        ["MATNR", "WERKS", "EKGRP", "DISMM", "DISPO", "DISLS", "BESKZ",
         "SOBSL", "LGPRO", "LGFSB", "PLIFZ", "WEBAZ", "EISBE", "BSTMI",
         "BSTMA", "BSTFE", "BSTRF", "MABST", "LOSGR", "SBDKZ", "LAGPR",
         "ALTSL", "KZAUS", "AUSSS", "AUSDT", "NFMAT", "SERNP", "STDPD",
         "STLNR", "MINBE", "SHZET", "DZEIT", "FHORI", "FXHOR", "STRGR",
         "PRCTR", "VRMOD", "VINT1", "VINT2"],
        "WERKS IN ({werks})",
    ),
    "MARD": (
        ["MATNR", "WERKS", "LGORT", "LABST", "INSME", "EINME", "SPEME",
         "RETME", "UMLME"],
        "WERKS IN ({werks})",
    ),
    "MARM": (
        ["MATNR", "MEINH", "UMREZ", "UMREN", "LAENG", "BREIT", "HOEHE",
         "MEABM", "VOLUM", "VOLEH", "BRGEW", "GEWEI"],
        "",  # All UOM conversions for materials in scope
    ),
    "MVKE": (
        ["MATNR", "VKORG", "VTWEG", "KONDM", "KTGRM", "MVGR1", "MVGR2",
         "MVGR3", "PRODH", "PMATN"],
        "",
    ),
    "MBEW": (
        ["MATNR", "BWKEY", "VPRSV", "VERPR", "STPRS", "PEINH", "BKLAS",
         "LBKUM", "SALK3", "BWTAR"],
        "BWKEY IN ({werks})",
    ),
    "LFA1": (
        ["LIFNR", "LAND1", "NAME1", "NAME2", "ORT01", "PSTLZ", "REGIO",
         "STRAS", "ADRNR", "KTOKK", "SPRAS", "TELF1", "ERDAT", "SPERM"],
        "",  # All vendors
    ),
    "KNA1": (
        ["KUNNR", "LAND1", "NAME1", "NAME2", "ORT01", "PSTLZ", "REGIO",
         "STRAS", "ADRNR", "KTOKD", "SPRAS", "TELF1", "ERDAT", "AUFSD"],
        "",  # All customers
    ),
    "KNVV": (
        ["KUNNR", "VKORG", "VTWEG", "SPART", "BZIRK", "KDGRP", "VWERK",
         "WAERS"],
        "",
    ),
    "EINA": (
        ["INFNR", "MATNR", "LIFNR", "LOEKZ", "ERDAT", "TXZ01", "MEINS"],
        "",
    ),
    "EINE": (
        ["INFNR", "EKORG", "ESOKZ", "WERKS", "NETPR", "PEINH", "BPRME",
         "APLFZ", "PLIFZ", "NORBM", "MINBM", "UEBTK", "UEBTO", "UNTTO",
         "MWSKZ", "LIFNR", "WAERS"],
        "",
    ),
    "EORD": (
        ["MATNR", "WERKS", "ZEESSION", "LIFNR", "FLIFN", "EKORG", "VDATU",
         "BDATU", "NOTKZ"],
        "WERKS IN ({werks})",
    ),
    "EBAN": (
        ["BANFN", "BNFPO", "MATNR", "WERKS", "LGORT", "MENGE", "MEINS",
         "BADAT", "LFDAT", "FRGST", "LOEKZ", "EBAKZ", "STATU"],
        "WERKS IN ({werks})",
    ),
    "CRHD": (
        ["OBJID", "OBJTY", "ARBPL", "WERKS", "VERWE", "KTEXT"],
        "WERKS IN ({werks})",
    ),
    "EQUI": (
        ["EQUNR", "EQART", "EQTYP", "HERST", "TYPBZ", "BRGEW", "GEWEI",
         "ANSDT", "BAUJJ", "BAUMM"],
        "",
    ),
    # BOM
    "STKO": (
        ["STLNR", "STLAL", "STEFM", "STLST", "DATUV", "BMENG",
         "BMEIN", "STLTY", "STKTX", "LOEKZ"],
        "",
    ),
    "STPO": (
        ["STLNR", "STLKN", "STPOZ", "IDNRK", "MENGE", "MEINS", "AUSCH",
         "POTX1", "POSTP", "POSNR", "SORTF"],
        "",
    ),
    # Routing
    "PLKO": (
        ["PLNTY", "PLNNR", "PLNAL", "WERKS", "LOEKZ", "VERWE", "STATU",
         "PLNME", "BMSCH"],
        "WERKS IN ({werks})",
    ),
    "PLPO": (
        ["PLNTY", "PLNNR", "PLNAL", "VORNR", "STEUS", "LTXA1", "ARBID",
         "WERKS", "BMSCH", "MESSION", "VGE01", "VGW01", "VGE02", "VGW02",
         "VGE03", "VGW03", "RUESSION", "RSTZE"],
        "WERKS IN ({werks})",
    ),
    # Demand
    "PBIM": (
        ["BESSION", "MATNR", "WERKS", "BEDAE", "VERSB"],
        "WERKS IN ({werks})",
    ),
    "PBED": (
        ["BESSION", "PDATU", "PLNMG"],
        "",
    ),
    "PLAF": (
        ["PLNUM", "MATNR", "PLWRK", "PSTTR", "PEDTR", "GSMNG", "MEINS",
         "PLART", "FLAGE", "STATU"],
        "PLWRK IN ({werks})",
    ),
    "TJ02T": (
        ["ISTAT", "TXT04", "TXT30", "SPRAS"],
        "SPRAS = 'E'",
    ),

    # ── Transaction Data (Phase 3) — needed for lane inference ─────────
    "EKKO": (
        ["EBELN", "BUKRS", "BSTYP", "BSART", "LIFNR", "EKORG", "EKGRP",
         "WAERS", "BEDAT", "KDATB", "KDATE", "PROCSTAT", "RLWRT"],
        "BUKRS = '{bukrs}'",
    ),
    "EKPO": (
        ["EBELN", "EBELP", "MATNR", "WERKS", "LGORT", "MENGE", "MEINS",
         "NETPR", "PEINH", "BPRME", "TXZ01", "ELIKZ", "MATKL", "PSTYP",
         "KNTTP", "LOEKZ", "RETPO"],
        "WERKS IN ({werks})",
    ),
    "EKET": (
        ["EBELN", "EBELP", "ETENR", "EINDT", "SLFDT", "MENGE", "WEMNG",
         "DABMG"],
        "",
    ),
    "VBAK": (
        ["VBELN", "AUART", "VKORG", "VTWEG", "SPART", "KUNNR", "BSTNK",
         "ERDAT", "NETWR", "WAERK", "VDATU", "BNDDT", "GBSTK", "ABSTK"],
        "",
    ),
    "VBAP": (
        ["VBELN", "POSNR", "MATNR", "WERKS", "LGORT", "KWMENG", "VRKME",
         "NETWR", "WAERK", "ABGRU", "PSTYV", "PRODH"],
        "WERKS IN ({werks})",
    ),
    "LIKP": (
        ["VBELN", "KUNNR", "WADAT", "WADAT_IST", "LFART", "VSTEL",
         "ROUTE", "BTGEW", "GEWEI", "ERDAT", "ERNAM", "BOLNR", "LIFNR",
         "LFDAT", "LDDAT", "NTGEW", "VOLUM", "VOLEH", "VKORG"],
        "",
    ),
    "LIPS": (
        ["VBELN", "POSNR", "MATNR", "WERKS", "LGORT", "LFIMG", "MEINS",
         "VGBEL", "VGPOS", "PSTYV"],
        "WERKS IN ({werks})",
    ),
    # Production orders
    "AFKO": (
        ["AUFNR", "RSNUM", "PLNBEZ", "GAMNG", "GMEIN", "GSTRP", "GLTRP",
         "FTRMS", "DESSION", "PLNNR", "PLNAL"],
        "",
    ),
    "AFPO": (
        ["AUFNR", "POSNR", "MATNR", "PWERK", "DESSION", "PSMNG", "AMESSION",
         "WEMNG"],
        "PWERK IN ({werks})",
    ),
    "RESB": (
        ["RSNUM", "RSPOS", "MATNR", "WERKS", "LGORT", "BDMNG", "MEINS",
         "ENMNG", "AUFNR"],
        "WERKS IN ({werks})",
    ),
    "MKPF": (
        ["MBLNR", "MJAHR", "BLDAT", "BUDAT", "USNAM", "TCODE", "XBLNR",
         "BKTXT"],
        "BUDAT >= ADD_DAYS(CURRENT_DATE, -365)",
    ),
    "MSEG": (
        ["MBLNR", "MJAHR", "ZEESSION", "BWART", "MATNR", "WERKS", "LGORT",
         "CHARG", "MENGE", "MEINS", "EBELN", "EBELP", "LIFNR", "KUNNR",
         "UMWRK", "UMLGO", "SHKZG", "DMBTR", "BUDAT_MKPF"],
        "WERKS IN ({werks})",
    ),
    # Production order operations (routing steps with setup/run times)
    "AFVC": (
        ["AUFPL", "APLZL", "VORNR", "STEUS", "LTXA1", "ARBID", "WERKS",
         "BMSCH", "VGE01", "VGW01", "VGE02", "VGW02", "VGE03", "VGW03",
         "RUESSION", "RSTZE", "SSESSION", "ARBEI"],
        "",
    ),
    # Production order confirmations (actual yield/scrap/times)
    "AFRU": (
        ["RUESSION", "AUFNR", "VORNR", "LMNGA", "XMNGA", "RMNGA", "MESSION",
         "ISM01", "ISM02", "ISM03", "ISM04", "ISM05", "ISM06",
         "ILE01", "ILE02", "ILE03", "BUDAT", "ERSDA"],
        "",
    ),
    # SO schedule lines (promised delivery dates for ATP)
    "VBEP": (
        ["VBELN", "POSNR", "ETENR", "ETTYP", "EDATU", "EZEIT", "WMENG",
         "BMENG", "LMENG", "MEINS"],
        "",
    ),
    # PO history — goods receipts & invoice receipts (vendor performance)
    "EKBE": (
        ["EBELN", "EBELP", "ZEESSION", "VGABE", "BEWTP", "BWART", "BUDAT",
         "MENGE", "DMBTR", "WAERS", "SHKZG", "MATNR", "WERKS", "LIFNR",
         "XBLNR", "LFBNR", "CPUDT"],
        "EBELN IN (SELECT DISTINCT \"EBELN\" FROM {schema}.\"EKPO\" WHERE \"WERKS\" IN ({werks}))",
    ),
    # Pricing conditions (contract prices, discounts, surcharges)
    "KONV": (
        ["KNUMV", "KPOSN", "STUNR", "ZAESSION", "KSCHL", "KBETR", "WAERS",
         "KPEIN", "KMEIN", "KUMZA", "KUMNE", "KWERT", "KINAK"],
        "",
    ),
    # Work center cost assignments (cost rates for capacity planning)
    "CRCO": (
        ["OBJID", "VEESSION", "KOSTL", "LSTAR", "BUKRS"],
        "",
    ),
    # Quality inspection results detail
    "QASE": (
        ["PRUESSION", "VESSION", "VERWESSION", "MERESSION", "STESSION",
         "MITESSION", "ERESSION"],
        "",
    ),
    # Change document headers (master data change audit trail)
    "CDHDR": (
        ["OBJECTCLAS", "OBJECTID", "CHANGENR", "USERNAME", "UDATE", "UTIME",
         "TCODE", "CHANGE_IND"],
        "UDATE >= ADD_DAYS(CURRENT_DATE, -365)",
    ),
    # Change document items (which fields changed)
    "CDPOS": (
        ["OBJECTCLAS", "OBJECTID", "CHANGENR", "TABNAME", "FNAME",
         "CHNGIND", "VALUE_NEW", "VALUE_OLD"],
        "OBJECTID IN (SELECT \"OBJECTID\" FROM {schema}.\"CDHDR\" WHERE \"UDATE\" >= ADD_DAYS(CURRENT_DATE, -365))",
    ),

    # ── Additional tables for full AWS SC coverage ───────────────────

    # Product hierarchy (decode MARA.PRDHA → ProductHierarchy entity)
    "T179": (
        ["PRODH", "STUFE", "VESSION"],
        "",
    ),
    "T179T": (
        ["PRODH", "SPRAS", "VTEXT"],
        "SPRAS = 'E'",
    ),

    # Customer sales area data (customer distribution channel assignments)
    "KNVV": (
        ["KUNNR", "VKORG", "VTWEG", "SPART", "BZIRK", "KDGRP", "VWERK",
         "WAERS", "KALKS", "LPRIO"],
        "",
    ),

    # Batch/lot master data (for ShipmentLot traceability)
    "MCH1": (
        ["MATNR", "CHARG", "ERDAT", "ERSDA", "VEESSION"],
        "",
    ),
    "MCHA": (
        ["MATNR", "CHARG", "WERKS", "HSDAT", "VFDAT", "MAXLZ_MCHA",
         "LIESSION"],
        "",
    ),

    # SO header / item status (for OutboundOrderLine + Backorder status)
    "VBUK": (
        ["VBELN", "LFSTK", "WBSTK", "FKSTK", "GBSTK", "ABSTK", "KOSTK"],
        "",
    ),
    "VBUP": (
        ["VBELN", "POSNR", "LFSTA", "WBSTA", "FKSTA", "GBSTA", "ABSTA",
         "KOSTA"],
        "",
    ),

    # Internal orders (production, maintenance, investment orders)
    "AUFK": (
        ["AUFNR", "AUART", "AUTYP", "WERKS", "ERDAT", "BUKRS", "KTEXT",
         "OBJNR", "WAERS", "LOESSION"],
        "",
    ),

    # Object system status (status of orders, deliveries, etc.)
    "JEST": (
        ["OBJNR", "STAT", "INACT"],
        "",
    ),

    # Quality inspection lots (QC status for inbound/production)
    "QALS": (
        ["PRUEFLOS", "MATNR", "WERK", "ART", "HERKUNFT", "STAT",
         "ENSTEHDAT", "PASTRTERM", "PAENDTERM", "LOSMENGE", "MENGENEINH",
         "AUFNR", "CHARG", "INSMK"],
        "",
    ),
    # Quality notifications (defects, complaints)
    "QMEL": (
        ["QMNUM", "QMART", "MATNR", "ERDAT", "PRIOK", "STRMN", "LTRMN",
         "QMTXT", "AUFNR", "OBJNR"],
        "",
    ),

    # Transfer orders (warehouse movements for FulfillmentOrder)
    "LTAK": (
        ["TANUM", "LGNUM", "TBNUM", "BWART", "BWLVS", "BDATU", "BZEIT",
         "LZNUM", "BETYP", "BENUM", "TRART", "STDAT", "ENDAT"],
        "",
    ),
    "LTAP": (
        ["LGNUM", "TANUM", "TAPOS", "MATNR", "WERKS", "LGORT", "VLTYP",
         "VLPLA", "NLTYP", "NLPLA", "VSOLM", "NSOLM", "VISTM", "NISTM",
         "MEINS"],
        "",
    ),

    # PO history (goods receipts for vendor performance + InboundOrder actuals)
    "EKBE": (
        ["EBELN", "EBELP", "ZEESSION", "VGABE", "BEWTP", "BWART", "BUDAT",
         "MENGE", "DMBTR", "WAERS", "SHKZG", "MATNR", "WERKS", "LIFNR",
         "XBLNR", "LFBNR", "CPUDT"],
        "",
    ),

    # Capacity planning (work center capacity for ProductionCapacity)
    "KAKO": (
        ["OBJID", "DATUB", "DATBI", "KAPESSION", "AESSION",
         "ANESSION", "BEGZT", "ENDZT"],
        "",
    ),
}

# Tables to extract by default (the full set)
DEFAULT_TABLES = list(SAP_TABLES.keys())

# Transaction tables only (for incremental extraction)
TRANSACTION_TABLES = [
    "EKKO", "EKPO", "EKET", "EKBE", "VBAK", "VBAP", "VBEP", "VBUK", "VBUP",
    "LIKP", "LIPS", "LTAK", "LTAP",
    "AFKO", "AFPO", "AFVC", "AFRU", "RESB", "MKPF", "MSEG",
    "KONV", "QASE", "QALS", "QMEL", "AUFK", "JEST",
]


def get_plants_for_company(conn, company_code: str) -> List[str]:
    """Query T001W to get all plants belonging to a company code."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT WERKS FROM T001W WHERE BUKRS = ?",
        (company_code,),
    )
    plants = [row[0] for row in cursor.fetchall()]
    cursor.close()
    logger.info(f"Found {len(plants)} plants for company code {company_code}: {plants}")
    return plants


def get_address_numbers(conn, plants: List[str]) -> List[str]:
    """Get ADRNR values from T001W for ADRC filtering."""
    if not plants:
        return []
    placeholders = ",".join(["?"] * len(plants))
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT DISTINCT ADRNR FROM T001W WHERE WERKS IN ({placeholders})",
        plants,
    )
    addrs = [row[0] for row in cursor.fetchall() if row[0]]
    cursor.close()
    return addrs


def extract_table(
    conn,
    table_name: str,
    company_code: str,
    plants: List[str],
    address_numbers: Optional[List[str]] = None,
    row_limit: int = 0,
) -> Tuple[List[str], List[List[str]]]:
    """
    Extract a single SAP table, applying company/plant filters where defined.

    Returns (column_names, rows).
    """
    if table_name not in SAP_TABLES:
        raise ValueError(f"Unknown table: {table_name}")

    columns, where_template = SAP_TABLES[table_name]
    col_list = ", ".join(f'"{c}"' for c in columns)

    # Build WHERE clause
    where_parts = []
    params = []

    if where_template:
        if "{bukrs}" in where_template:
            where_parts.append(f"\"BUKRS\" = ?")
            params.append(company_code)
        elif "{werks}" in where_template:
            if plants:
                placeholders = ",".join(["?"] * len(plants))
                # Find the column name from the template
                col = where_template.split(" IN ")[0].strip()
                if col == "WERKS IN ({werks})":
                    col = "WERKS"
                elif "WERKS" in where_template:
                    col = "WERKS"
                elif "PLWRK" in where_template:
                    col = "PLWRK"
                elif "PWERK" in where_template:
                    col = "PWERK"
                elif "BWKEY" in where_template:
                    col = "BWKEY"
                else:
                    col = where_template.split()[0]
                where_parts.append(f'"{col}" IN ({placeholders})')
                params.extend(plants)
        elif where_template.startswith("SPRAS"):
            where_parts.append('"SPRAS" = ?')
            params.append("E")

    # Special case: ADRC — filter by address numbers from T001W + LFA1 + KNA1
    if table_name == "ADRC" and address_numbers:
        placeholders = ",".join(["?"] * len(address_numbers))
        where_parts.append(f'"ADDRNUMBER" IN ({placeholders})')
        params.extend(address_numbers)

    # Special cases for tables without direct BUKRS/WERKS filter
    # Filter MARA by materials that exist in MARC for our plants
    if table_name == "MARA" and plants:
        placeholders = ",".join(["?"] * len(plants))
        where_parts.append(
            f'"MATNR" IN (SELECT DISTINCT "MATNR" FROM "MARC" WHERE "WERKS" IN ({placeholders}))'
        )
        params.extend(plants)

    # Filter MARM/MVKE by materials in scope
    if table_name in ("MARM", "MVKE") and plants:
        placeholders = ",".join(["?"] * len(plants))
        where_parts.append(
            f'"MATNR" IN (SELECT DISTINCT "MATNR" FROM "MARC" WHERE "WERKS" IN ({placeholders}))'
        )
        params.extend(plants)

    # Filter MAKT by materials in scope
    if table_name == "MAKT" and plants:
        placeholders = ",".join(["?"] * len(plants))
        where_parts.append(
            f'"MATNR" IN (SELECT DISTINCT "MATNR" FROM "MARC" WHERE "WERKS" IN ({placeholders}))'
        )
        params.extend(plants)

    # Filter EINA/EINE by vendors that supply our plants
    if table_name in ("EINA", "EINE") and plants:
        placeholders = ",".join(["?"] * len(plants))
        where_parts.append(
            f'"LIFNR" IN (SELECT DISTINCT "LIFNR" FROM "EORD" WHERE "WERKS" IN ({placeholders}))'
        )
        params.extend(plants)

    # Filter PBED by PBIM entries for our plants
    if table_name == "PBED" and plants:
        placeholders = ",".join(["?"] * len(plants))
        where_parts.append(
            f'"BESSION" IN (SELECT DISTINCT "BESSION" FROM "PBIM" WHERE "WERKS" IN ({placeholders}))'
        )
        params.extend(plants)

    # Filter EKET by EKPO entries for our plants
    if table_name == "EKET" and plants:
        placeholders = ",".join(["?"] * len(plants))
        where_parts.append(
            f'"EBELN" IN (SELECT DISTINCT "EBELN" FROM "EKPO" WHERE "WERKS" IN ({placeholders}))'
        )
        params.extend(plants)

    # Filter VBAK by sales orders that ship from our plants
    if table_name == "VBAK" and plants:
        placeholders = ",".join(["?"] * len(plants))
        where_parts.append(
            f'"VBELN" IN (SELECT DISTINCT "VBELN" FROM "VBAP" WHERE "WERKS" IN ({placeholders}))'
        )
        params.extend(plants)

    # Filter LIKP by deliveries from our plants
    if table_name == "LIKP" and plants:
        placeholders = ",".join(["?"] * len(plants))
        where_parts.append(
            f'"VBELN" IN (SELECT DISTINCT "VBELN" FROM "LIPS" WHERE "WERKS" IN ({placeholders}))'
        )
        params.extend(plants)

    # Filter AFKO by production orders for our plants
    if table_name == "AFKO" and plants:
        placeholders = ",".join(["?"] * len(plants))
        where_parts.append(
            f'"AUFNR" IN (SELECT DISTINCT "AUFNR" FROM "AFPO" WHERE "PWERK" IN ({placeholders}))'
        )
        params.extend(plants)

    # Build SQL
    where_clause = " AND ".join(where_parts) if where_parts else "1=1"
    limit_clause = f" LIMIT {row_limit}" if row_limit > 0 else ""
    sql = f'SELECT {col_list} FROM "{table_name}" WHERE {where_clause}{limit_clause}'

    logger.info(f"Extracting {table_name}...")
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        logger.info(f"  {table_name}: {len(rows)} rows")
        return columns, [list(row) for row in rows]
    except Exception as e:
        logger.error(f"  {table_name}: FAILED — {e}")
        return columns, []
    finally:
        cursor.close()


def save_csv(
    output_dir: Path,
    table_name: str,
    columns: List[str],
    rows: List[List[str]],
    label: str = "",
) -> Path:
    """Save extracted data as CSV file matching ingestion pipeline format."""
    # Use the naming convention expected by the ingestion pipeline
    # e.g., EKKO_purchase_order_headers.csv
    filename = f"{table_name}_{label}.csv" if label else f"{table_name}.csv"
    filepath = output_dir / filename

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in rows:
            # Convert None to empty string, handle date/time objects
            writer.writerow([
                "" if v is None else str(v) for v in row
            ])

    logger.info(f"  Saved {filepath} ({len(rows)} rows)")
    return filepath


# Friendly labels for CSV filenames
TABLE_LABELS = {
    "T001": "company_codes",
    "T001W": "plants",
    "T001L": "storage_locations",
    "ADRC": "addresses",
    "MARA": "materials",
    "MAKT": "descriptions",
    "MARC": "material_plant",
    "MARD": "stock",
    "MARM": "uom_conversions",
    "MVKE": "sales_data",
    "MBEW": "valuation",
    "LFA1": "vendors",
    "KNA1": "customers",
    "KNVV": "customer_sales_area",
    "EINA": "purchasing_info_general",
    "EINE": "purchasing_info_org",
    "EORD": "source_list",
    "EBAN": "purchase_requisitions",
    "CRHD": "work_centers",
    "EQUI": "equipment",
    "STKO": "bom_headers",
    "STPO": "bom_items",
    "PLKO": "routing_headers",
    "PLPO": "routing_operations",
    "PBIM": "pir_header",
    "PBED": "pir_schedule",
    "PLAF": "planned_orders",
    "TJ02T": "status_texts",
    "EKKO": "purchase_order_headers",
    "EKPO": "purchase_order_items",
    "EKET": "po_schedule_lines",
    "VBAK": "sales_order_headers",
    "VBAP": "sales_order_items",
    "LIKP": "delivery_headers",
    "LIPS": "delivery_items",
    "AFKO": "production_order_headers",
    "AFPO": "production_order_items",
    "RESB": "reservations",
    "MKPF": "material_document_headers",
    "MSEG": "goods_movements",
    "AFVC": "production_order_operations",
    "AFRU": "production_confirmations",
    "VBEP": "sales_order_schedule_lines",
    "EKBE": "purchase_order_history",
    "KONV": "pricing_conditions",
    "CRCO": "work_center_costs",
    "QASE": "inspection_results",
    "CDHDR": "change_document_headers",
    "CDPOS": "change_document_items",
    "T179": "product_hierarchy",
    "T179T": "product_hierarchy_text",
    "KNVV": "customer_sales_area",
    "MCH1": "batch_master",
    "MCHA": "batch_plant",
    "VBUK": "sales_header_status",
    "VBUP": "sales_item_status",
    "AUFK": "orders",
    "JEST": "system_status",
    "QALS": "inspection_lots",
    "QMEL": "quality_notifications",
    "LTAK": "transfer_order_headers",
    "LTAP": "transfer_order_items",
    "KAKO": "capacity_headers",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract SAP tables from HANA database for Autonomy ingestion",
    )
    parser.add_argument("--host", help="HANA host (or SAP_HANA_HOST env)")
    parser.add_argument("--port", type=int, default=30015, help="HANA port (default: 30015)")
    parser.add_argument("--instance", type=int, help="SAP instance number (alternative to --port, sets port to 3<NN>15)")
    parser.add_argument("--user", help="HANA user (or SAP_HANA_USER env)")
    parser.add_argument("--password", help="HANA password (or SAP_HANA_PASSWORD env)")
    parser.add_argument("--schema", help="HANA schema (default: auto-detect from user)")
    parser.add_argument("--company-code", default="1710", help="SAP company code (default: 1710)")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory (default: sap_extract_<timestamp>)")
    parser.add_argument(
        "--tables",
        help="Comma-separated list of tables to extract (default: all)",
    )
    parser.add_argument(
        "--transactions-only",
        action="store_true",
        help="Extract only transaction tables (EKKO,EKPO,VBAK,VBAP,LIKP,LIPS,...)",
    )
    parser.add_argument(
        "--row-limit",
        type=int,
        default=0,
        help="Max rows per table (0 = unlimited, useful for testing)",
    )
    parser.add_argument("--env-file", type=Path, help="Load connection from .env file")
    parser.add_argument("--dry-run", action="store_true", help="Show SQL without executing")
    return parser.parse_args()


def main():
    args = parse_args()

    # Load env file if specified
    if args.env_file and args.env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(args.env_file)

    # Resolve connection parameters
    host = args.host or os.environ.get("SAP_HANA_HOST")
    port = args.port
    if args.instance is not None:
        port = 30000 + args.instance * 100 + 15
    port = int(os.environ.get("SAP_HANA_PORT", port))
    user = args.user or os.environ.get("SAP_HANA_USER")
    password = args.password or os.environ.get("SAP_HANA_PASSWORD")
    company_code = args.company_code or os.environ.get("SAP_COMPANY_CODE", "1710")

    if not host or not user or not password:
        print("\nSAP HANA Connection Details Required")
        print("=" * 40)
        if not host:
            host = input("HANA Host (IP or hostname): ").strip()
        if not user:
            user = input("HANA User [SAPHANADB]: ").strip() or "SAPHANADB"
        if not password:
            import getpass
            password = getpass.getpass("HANA Password: ")
        port_input = input(f"HANA Port [{port}]: ").strip()
        if port_input:
            port = int(port_input)
        cc_input = input(f"Company Code [{company_code}]: ").strip()
        if cc_input:
            company_code = cc_input

    # Determine which tables to extract
    if args.tables:
        tables_to_extract = [t.strip().upper() for t in args.tables.split(",")]
    elif args.transactions_only:
        tables_to_extract = TRANSACTION_TABLES
    else:
        tables_to_extract = DEFAULT_TABLES

    # Validate table names
    unknown = [t for t in tables_to_extract if t not in SAP_TABLES]
    if unknown:
        logger.error(f"Unknown tables: {unknown}")
        logger.info(f"Known tables: {sorted(SAP_TABLES.keys())}")
        return 1

    # Output directory
    output_dir = args.output_dir or Path(f"sap_extract_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Connecting to HANA at {host}:{port} as {user}")
    logger.info(f"Company code: {company_code}")
    logger.info(f"Tables to extract: {len(tables_to_extract)}")
    logger.info(f"Output: {output_dir.absolute()}")

    if args.dry_run:
        logger.info("DRY RUN — showing queries without executing")
        for table in tables_to_extract:
            columns, where_template = SAP_TABLES[table]
            print(f"\n-- {table}")
            print(f"SELECT {', '.join(columns)}")
            print(f"FROM {table}")
            if where_template:
                print(f"WHERE {where_template}")
        return 0

    # Connect
    try:
        import hdbcli.dbapi as dbapi
    except ImportError:
        logger.error(
            "hdbcli not installed. Install with: pip install hdbcli\n"
            "Or download from: https://tools.hana.ondemand.com/#hanatools"
        )
        return 1

    try:
        conn = dbapi.connect(
            address=host,
            port=port,
            user=user,
            password=password,
            autocommit=True,
        )
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        logger.info("Common issues:")
        logger.info(f"  - Port: Try 3<instance>15 (e.g., 30015 for instance 00)")
        logger.info(f"  - User: Try SAPHANADB, SYSTEM, or SAP<SID>")
        logger.info(f"  - Firewall: Ensure port {port} is open on {host}")
        return 1

    logger.info("Connected to HANA successfully")

    # Set schema if specified
    if args.schema:
        conn.cursor().execute(f'SET SCHEMA "{args.schema}"')

    try:
        # Get plants for company code
        plants = get_plants_for_company(conn, company_code)
        if not plants:
            logger.warning(f"No plants found for company code {company_code}")
            logger.info("Proceeding without plant filter...")

        # Get address numbers for ADRC filtering
        address_numbers = get_address_numbers(conn, plants)
        # Also get vendor and customer addresses
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT "ADRNR" FROM "LFA1" WHERE "ADRNR" IS NOT NULL')
            address_numbers.extend([r[0] for r in cursor.fetchall()])
            cursor.execute('SELECT DISTINCT "ADRNR" FROM "KNA1" WHERE "ADRNR" IS NOT NULL')
            address_numbers.extend([r[0] for r in cursor.fetchall()])
            cursor.close()
        except Exception:
            pass
        address_numbers = list(set(address_numbers))

        # Extract each table
        results = {}
        total = len(tables_to_extract)
        for i, table_name in enumerate(tables_to_extract, 1):
            logger.info(f"[{i}/{total}] Extracting {table_name}...")
            columns, rows = extract_table(
                conn, table_name, company_code, plants,
                address_numbers=address_numbers,
                row_limit=args.row_limit,
            )
            results[table_name] = (columns, rows)

            # Save immediately
            label = TABLE_LABELS.get(table_name, "")
            save_csv(output_dir, table_name, columns, rows, label)

        # Summary
        print(f"\n{'=' * 60}")
        print(f"Extraction Complete — {output_dir.absolute()}")
        print(f"{'=' * 60}")
        print(f"{'Table':<30} {'Rows':>10}")
        print(f"{'-' * 30} {'-' * 10}")
        total_rows = 0
        for table_name in tables_to_extract:
            columns, rows = results[table_name]
            print(f"{table_name + '_' + TABLE_LABELS.get(table_name, ''):<30} {len(rows):>10}")
            total_rows += len(rows)
        print(f"{'-' * 30} {'-' * 10}")
        print(f"{'TOTAL':<30} {total_rows:>10}")
        print(f"\nUpload these CSV files via SAP Data Management > Start Job")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
