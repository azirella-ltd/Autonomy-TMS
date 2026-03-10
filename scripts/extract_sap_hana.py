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
            "autonomy_target": "InboundOrder / OutboundOrderLine (shipments)",
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
            "autonomy_target": "InboundOrderLine / OutboundOrderLine (delivery qty, reference to SO/PO)",
        },
        # --- NEW: Transfer Orders (warehouse-internal moves) ---
        {
            "name": "Transfer Order Headers",
            "filename": "LTAK_transfer_orders.csv",
            "query": f"""
                SELECT TANUM, LGNUM, TBNUM, BWART, BWLVS, BDATU,
                       BZEIT, LZNUM, BETYP, BENUM, TRART, STDAT, ENDAT
                FROM {SCHEMA}.LTAK
                WHERE LGNUM IN (SELECT LGNUM FROM {SCHEMA}.T300)
                ORDER BY TANUM
            """,
            "autonomy_target": "TransferOrder (TO execution TRM, inventory rebalancing TRM)",
            "notes": "T300 links LGNUM (warehouse) to plant. TRART=transfer type, STDAT/ENDAT=start/end.",
        },
        {
            "name": "Transfer Order Items",
            "filename": "LTAP_transfer_order_items.csv",
            "query": f"""
                SELECT i.LGNUM, i.TANUM, i.TAPOS, i.MATNR,
                       i.WERKS, i.LGORT, i.VLTYP, i.VLPLA,
                       i.NLTYP, i.NLPLA, i.VSOLM, i.NSOLM,
                       i.VISTM, i.NISTM, i.MEINS
                FROM {SCHEMA}.LTAP i
                WHERE i.LGNUM IN (SELECT LGNUM FROM {SCHEMA}.T300)
                ORDER BY i.TANUM, i.TAPOS
            """,
            "autonomy_target": "TransferOrder line items (product, qty, source/dest bin). "
                               "VLTYP/VLPLA=source, NLTYP/NLPLA=dest, VSOLM=source qty, NSOLM=dest qty.",
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
            "autonomy_target": "QualityOrder (quality disposition TRM)",
        },
        # --- NEW: Quality Inspection Lots ---
        {
            "name": "Quality Inspection Lots",
            "filename": "QALS_inspection_lots.csv",
            "query": f"""
                SELECT PRUEFLOS, MATNR, WERK, ART, HERKUNFT,
                       BEARBSTATU, ENSTEHDAT, ENTSTEZEIT,
                       PASTRTERM, PAENDTERM, LOSMENGE, MENGENEINH,
                       AUFNR, CHARG, INSMK
                FROM {SCHEMA}.QALS
                WHERE WERK IN (SELECT WERKS FROM {SCHEMA}.T001W WHERE {SALES_ORG_FILTER})
                ORDER BY PRUEFLOS
            """,
            "autonomy_target": "QualityOrder — open inspection lots feed QualityDispositionTRM. "
                               "BEARBSTATU=processing status, INSMK=stock posting (blocked/unrestricted). "
                               "PASTRTERM/PAENDTERM=plan start/end for scheduling.",
        },
        {
            "name": "Quality Inspection Results",
            "filename": "QASE_inspection_results.csv",
            "query": f"""
                SELECT r.PRUEFLOS, r.VORGLFNR, r.MERKNR,
                       r.MESSWERT, r.MBEWERTG, r.ANZFEHLER,
                       r.CODE1, r.VERSION1,
                       r.ERSTELLDAT, r.PRUEFER
                FROM {SCHEMA}.QASE r
                WHERE r.PRUEFLOS IN (
                    SELECT PRUEFLOS FROM {SCHEMA}.QALS
                    WHERE WERK IN (SELECT WERKS FROM {SCHEMA}.T001W WHERE {SALES_ORG_FILTER})
                )
                ORDER BY r.PRUEFLOS, r.VORGLFNR
            """,
            "autonomy_target": "QualityOrder inspection results — MBEWERTG=valuation (A=accept, R=reject), "
                               "MESSWERT=measured value, ANZFEHLER=defect count. Feeds QualityDispositionTRM training data.",
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
            "autonomy_target": "MaintenanceOrder (maintenance scheduling TRM); also parent for prod orders",
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
            "autonomy_target": "Asset/Resource — maintenance scheduling TRM asset registry",
        },
        # --- NEW: PM/PP Order Operations ---
        {
            "name": "Order Operations (PP/PM)",
            "filename": "AFVC_order_operations.csv",
            "query": f"""
                SELECT v.AUFPL, v.APLZL, v.VORNR, v.ARBID, v.WERKS,
                       v.STEUS, v.LTXA1, v.LIFNR, v.PREIS, v.WAERS
                FROM {SCHEMA}.AFVC v
                WHERE v.WERKS IN (SELECT WERKS FROM {SCHEMA}.T001W WHERE {SALES_ORG_FILTER})
                ORDER BY v.AUFPL, v.APLZL
            """,
            "autonomy_target": "MaintenanceOrder / ManufacturingOrder operations. "
                               "VORNR=operation number, ARBID=work center, STEUS=control key. "
                               "Links to AUFK via AUFPL (routing number). "
                               "Feeds MOExecutionTRM (sequencing, changeover) and MaintenanceSchedulingTRM.",
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
            "autonomy_target": "InvLevel (on_hand, in_transit, quality_inspection, blocked)",
        },
        # --- NEW: Goods Movement History ---
        {
            "name": "Goods Movement Headers",
            "filename": "MKPF_goods_movement_headers.csv",
            "query": f"""
                SELECT MBLNR, MJAHR, BLDAT, BUDAT, BKTXT,
                       USNAM, XBLNR
                FROM {SCHEMA}.MKPF
                WHERE BUDAT >= ADD_DAYS(CURRENT_DATE, -365)
                ORDER BY BUDAT DESC, MBLNR
            """,
            "autonomy_target": "Inventory transaction history — 12-month rolling for CDC baseline and trend analysis",
        },
        {
            "name": "Goods Movement Items",
            "filename": "MSEG_goods_movement_items.csv",
            "query": f"""
                SELECT s.MBLNR, s.MJAHR, s.ZEILE, s.BWART,
                       s.MATNR, s.WERKS, s.LGORT, s.MENGE,
                       s.MEINS, s.SHKZG, s.AUFNR, s.EBELN, s.EBELP,
                       s.LIFNR, s.KUNNR, s.KDAUF, s.SOBKZ, s.DMBTR,
                       s.BUDAT_MKPF
                FROM {SCHEMA}.MSEG s
                WHERE s.WERKS IN (SELECT WERKS FROM {SCHEMA}.T001W WHERE {SALES_ORG_FILTER})
                AND s.MJAHR >= YEAR(ADD_DAYS(CURRENT_DATE, -365))
                ORDER BY s.MBLNR, s.MJAHR, s.ZEILE
            """,
            "autonomy_target": "InvLevel history (receipts=101/103, issues=201/261, transfers=301/311, scrap=551). "
                               "Movement type (BWART) determines transaction type. CRITICAL for: "
                               "(1) demand sensing — actual consumption vs forecast, "
                               "(2) lead time computation — GR date vs PO date, "
                               "(3) yield analysis — planned vs actual production qty, "
                               "(4) CDC baseline — rolling inventory flow for change detection",
        },
    ],

    # --- NEW CATEGORY: order_status ---
    # System and user statuses for all order types.
    # CRITICAL for knowing which orders are in-progress vs complete.
    "order_status": [
        {
            "name": "Object System Status (JEST)",
            "filename": "JEST_system_status.csv",
            "query": f"""
                SELECT j.OBJNR, j.STAT, j.INACT
                FROM {SCHEMA}.JEST j
                WHERE j.OBJNR LIKE 'OR%'
                AND j.INACT = ''
                AND EXISTS (
                    SELECT 1 FROM {SCHEMA}.AUFK a
                    WHERE a.OBJNR = j.OBJNR AND a.{PLANT_FILTER}
                )
                ORDER BY j.OBJNR, j.STAT
            """,
            "autonomy_target": "Order status for MO/PM orders. Maps to ManufacturingOrder.status, MaintenanceOrder.status. "
                               "Key statuses: I0001=Created, I0002=Released, I0009=CNF (confirmed), I0046=TECO (technically complete), I0045=DLV (delivered). "
                               "CRITICAL: determines which MOs/POs/TOs are in-progress for TRM execution decisions.",
        },
        {
            "name": "Status Descriptions (TJ02T)",
            "filename": "TJ02T_status_texts.csv",
            "query": f"""
                SELECT ISTAT, SPRAS, TXT04, TXT30
                FROM {SCHEMA}.TJ02T
                WHERE SPRAS = 'E'
                ORDER BY ISTAT
            """,
            "autonomy_target": "Lookup table for JEST.STAT → human-readable status text. "
                               "Example: I0001→CRTD, I0002→REL, I0009→CNF, I0045→DLV, I0046→TECO.",
        },
        {
            "name": "Sales Document Item Status (VBUP)",
            "filename": "VBUP_sales_item_status.csv",
            "query": f"""
                SELECT p.VBELN, p.POSNR, p.LFSTA, p.WBSTA,
                       p.FKSTA, p.GBSTA, p.ABSTA, p.KOSTA
                FROM {SCHEMA}.VBUP p
                WHERE EXISTS (
                    SELECT 1 FROM {SCHEMA}.VBAK h
                    WHERE h.VBELN = p.VBELN AND h.{SALES_ORG_FILTER}
                )
                ORDER BY p.VBELN, p.POSNR
            """,
            "autonomy_target": "Per-item status for sales orders → OutboundOrderLine.status. "
                               "LFSTA=delivery status, WBSTA=goods issue status, FKSTA=billing status, GBSTA=overall status. "
                               "Values: A=not yet processed, B=partially processed, C=completely processed. "
                               "CRITICAL: orders with LFSTA=A or B are open/in-progress (unfulfilled demand for ATP TRM).",
            "notes": "VBUP/VBUK are deprecated in S/4HANA (empty tables). Use VBAK.GBSTK for header status. "
                     "In S/4, status is calculated on-the-fly from VBAP/LIPS/VBRP. Kept for ECC compatibility.",
        },
        {
            "name": "Sales Document Header Status (VBUK)",
            "filename": "VBUK_sales_header_status.csv",
            "query": f"""
                SELECT k.VBELN, k.LFSTK, k.WBSTK,
                       k.FKSTK, k.GBSTK, k.ABSTK, k.KOSTK
                FROM {SCHEMA}.VBUK k
                WHERE EXISTS (
                    SELECT 1 FROM {SCHEMA}.VBAK h
                    WHERE h.VBELN = k.VBELN AND h.{SALES_ORG_FILTER}
                )
                ORDER BY k.VBELN
            """,
            "autonomy_target": "Header-level sales order status → OutboundOrderLine aggregate status. "
                               "GBSTK: A=not processed, B=partially processed, C=fully processed.",
            "notes": "Deprecated in S/4HANA (empty). Fallback: VBAK.GBSTK already contains this.",
        },
    ],

    # --- NEW CATEGORY: forecasting ---
    # Planned Independent Requirements (PIR) = SAP's demand forecast.
    # CRITICAL for Autonomy demand planning; without this, forecasts are synthetic.
    "forecasting": [
        {
            "name": "PIR Header (Planned Independent Requirements)",
            "filename": "PBIM_pir_header.csv",
            "query": f"""
                SELECT BDZEI, BEDAE, VERSB, MATNR, WERKS, PBDNR
                FROM {SCHEMA}.PBIM
                WHERE {PLANT_FILTER}
                ORDER BY MATNR, WERKS
            """,
            "autonomy_target": "Forecast entity — PBIM links material+plant to PIR versions. "
                               "BDZEI = requirements index (links to PBED), VERSB = version (00=active). "
                               "Each PBIM row = one material-plant forecast series.",
        },
        {
            "name": "PIR Schedule Lines (Forecast Quantities)",
            "filename": "PBED_pir_schedule.csv",
            "query": f"""
                SELECT d.BDZEI, d.PDATU, d.PLNMG, d.MEINS, d.ENTMG
                FROM {SCHEMA}.PBED d
                WHERE d.BDZEI IN (
                    SELECT BDZEI FROM {SCHEMA}.PBIM WHERE {PLANT_FILTER}
                )
                ORDER BY d.BDZEI, d.PDATU
            """,
            "autonomy_target": "Forecast.forecast_quantity by date — PDATU=requirements date, PLNMG=planned qty, "
                               "ENTMG=firmed qty. Maps directly to Forecast(product_id, site_id, forecast_date, forecast_quantity). "
                               "CRITICAL: This is SAP's actual demand plan. Without it, Autonomy forecasts are synthetic.",
        },
    ],
}


# ============================================================================
# SAP → Autonomy Entity Mapping Reference
# ============================================================================
# This mapping documents how every extracted SAP table feeds into Autonomy's
# AWS SC data model. Used by the ingestion script (ingest_sap_csvs.py) and
# the SAP Data Management field mapping service.
#
# Format: SAP_TABLE → Autonomy Entity (fields)
#
# MASTER DATA:
#   T001   → Tenant (company_code, currency)
#   T001W  → Site (site_id, name, address, master_type)
#   T001L  → Site storage locations (sublocation detail)
#   MARA   → Product (product_id, base_uom, product_group)
#   MAKT   → Product.product_name (description lookup)
#   MARC   → Product-Site link (MRP params, procurement type, safety stock)
#            BESKZ: E=in-house→MANUFACTURER, F=external→buy from supplier
#            EISBE→InvPolicy.ss_quantity, MINBE→reorder point
#            DISMM→MRP type, DISPO→MRP controller, PLIFZ→planned delivery time
#   MBEW   → Product.unit_cost (VERPR=moving avg, STPRS=standard)
#   MVKE   → Product sales data (distribution channel, product hierarchy)
#   MARM   → UOM conversion factors
#   STKO   → ProductBOM header (BOM number, base qty)
#   STPO   → ProductBOM components (component material, qty per)
#   LFA1   → TradingPartner(tpartner_type='supplier') / Site(MARKET_SUPPLY)
#   KNA1   → TradingPartner(tpartner_type='customer') / Site(MARKET_DEMAND)
#   ADRC   → Site/TradingPartner address details
#   CRHD   → Resource/WorkCenter (capacity planning)
#
# SOURCING:
#   EINA   → VendorProduct (vendor-material link, description)
#   EINE   → VendorProduct pricing (NETPR/PEINH), VendorLeadTime (APLFZ)
#   EORD   → SourcingRule (source list: material→vendor→plant, priority)
#
# DEMAND (Outbound):
#   VBAK   → OutboundOrderLine header (order_date, customer, currency)
#   VBAP   → OutboundOrderLine (product, qty, price, plant)
#   VBEP   → OutboundOrderLine schedule lines (delivery dates, confirmed qty)
#
# PROCUREMENT (Inbound):
#   EKKO   → InboundOrder (PO header: vendor, date, currency)
#   EKPO   → InboundOrderLine (PO item: product, qty, price, plant)
#   EKET   → InboundOrderLine schedule (delivery dates, received qty)
#            WEMNG=goods received qty → InboundOrderLine.received_quantity
#   EBAN   → Planned procurement (purchase requisitions → future POs)
#
# MANUFACTURING:
#   AFKO   → ManufacturingOrder (prod order: material, qty, dates)
#   AFPO   → ManufacturingOrder items (output material, confirmed qty)
#   PLAF   → PlannedOrder (MRP output → future MO/PO/TO)
#            BESKZ: E=planned production, F=planned procurement
#   PLKO   → ProductionProcess / Routing header
#   PLPO   → ProductionProcess operations (work center, times)
#   RESB   → ManufacturingOrder component requirements (BOM explosion result)
#            Links AUFNR (prod order) → component MATNR+BDMNG (required qty)
#
# DISTRIBUTION:
#   LIKP   → Shipment header (outbound delivery → customer, inbound → vendor)
#            LFART: LF=outbound, EL=inbound, NL=inbound (returns)
#   LIPS   → Shipment line items (material, qty, reference to SO/PO)
#            VGBEL/VGPOS = preceding doc (sales order or PO)
#   LTAK   → TransferOrder header (warehouse-internal moves)
#   LTAP   → TransferOrder items (product, qty, source/dest bin)
#            Maps to InventoryRebalancingTRM and TOExecutionTRM decisions
#
# QUALITY:
#   QMEL   → QualityOrder notification (defect/issue report)
#   QALS   → QualityOrder inspection lot (in-progress quality holds)
#            ART=inspection type, STAT=status → QualityDispositionTRM
#   QASE   → QualityOrder inspection results (accept/reject history)
#
# MAINTENANCE:
#   AUFK   → MaintenanceOrder (PM/PP order header, status via OBJNR→JEST)
#   EQUI   → Asset registry (equipment for maintenance scheduling TRM)
#   AFVC   → MaintenanceOrder operations (work center, times)
#
# INVENTORY:
#   MARD   → InvLevel (on_hand=LABST, in_transit=UMLME, quality=INSME)
#   MKPF   → Inventory transaction header (goods movement doc, 12-month rolling)
#   MSEG   → Inventory transaction items (movement type → receipt/issue/transfer/scrap)
#            BWART mapping: 101=GR from PO, 103=GR from prod, 201=GI for cost center,
#            261=GI for prod order, 301=transfer posting, 311=stock transfer, 551=scrap
#            SHKZG: S=debit (receipt), H=credit (issue)
#            CRITICAL for: demand sensing, lead time calc, yield analysis, CDC baseline
#
# ORDER STATUS:
#   JEST   → All order statuses (MO, PM, QM via OBJNR)
#            I0001=Created, I0002=Released, I0009=Confirmed, I0045=Delivered, I0046=TECO
#   TJ02T  → Status code → text lookup
#   VBUP   → Sales item status (delivery/GI/billing per line)
#            LFSTA/GBSTA: A=open, B=partial, C=complete
#   VBUK   → Sales header status (aggregate)
#
# FORECASTING:
#   PBIM   → Forecast series header (material+plant+version)
#   PBED   → Forecast quantities by date → Forecast(forecast_date, forecast_quantity)
#            CRITICAL: SAP's actual demand plan. Version 00 = active forecast.
#
# ============================================================================


# ============================================================================
# Fuzzy Column Matching — adapts queries to actual S/4HANA version
# ============================================================================

# Cache of table -> set of column names
_table_columns_cache: Dict[str, set] = {}
# Cache of all table names in the schema
_all_tables_cache: set = set()


def get_all_tables(cursor) -> set:
    """Get all table names in the SAPHANADB schema."""
    global _all_tables_cache
    if _all_tables_cache:
        return _all_tables_cache
    try:
        cursor.execute(
            f"SELECT TABLE_NAME FROM SYS.TABLES WHERE SCHEMA_NAME='{SCHEMA}'"
        )
        _all_tables_cache = {row[0] for row in cursor.fetchall()}
        return _all_tables_cache
    except Exception:
        return set()


def fuzzy_match_table(cursor, table_name: str) -> str:
    """Find the best fuzzy match for a table name in the schema.

    S/4HANA versions may rename tables (e.g., VBUP deprecated, MATDOC replaces MKPF/MSEG).
    Returns the matched table name, or None if no reasonable match found.
    """
    all_tables = get_all_tables(cursor)
    if table_name in all_tables:
        return table_name

    # Case-insensitive exact
    for t in all_tables:
        if t.upper() == table_name.upper():
            return t

    # Substring match (e.g., if table was renamed with prefix/suffix)
    candidates = []
    for t in sorted(all_tables):
        if table_name.upper() in t.upper() or t.upper() in table_name.upper():
            candidates.append(t)
    if len(candidates) == 1:
        logger.info(f"    Table fuzzy match: {table_name} -> {candidates[0]} (substring)")
        return candidates[0]

    # Levenshtein distance <= 2
    best_tbl, best_dist = None, 999
    for t in all_tables:
        dist = _levenshtein(table_name.upper(), t.upper())
        if dist < best_dist:
            best_dist = dist
            best_tbl = t
    if best_dist <= 2:
        logger.info(f"    Table fuzzy match: {table_name} -> {best_tbl} (Levenshtein={best_dist})")
        return best_tbl

    return None


def get_table_columns(cursor, table_name: str) -> set:
    """Get actual column names for a table from HANA catalog.

    If the table doesn't exist, tries fuzzy matching to find the correct table name.
    """
    if table_name in _table_columns_cache:
        return _table_columns_cache[table_name]
    try:
        cursor.execute(
            f"SELECT COLUMN_NAME FROM SYS.TABLE_COLUMNS "
            f"WHERE SCHEMA_NAME='{SCHEMA}' AND TABLE_NAME='{table_name}'"
        )
        cols = {row[0] for row in cursor.fetchall()}
        if cols:
            _table_columns_cache[table_name] = cols
            return cols

        # Table not found — try fuzzy match
        matched = fuzzy_match_table(cursor, table_name)
        if matched and matched != table_name:
            cursor.execute(
                f"SELECT COLUMN_NAME FROM SYS.TABLE_COLUMNS "
                f"WHERE SCHEMA_NAME='{SCHEMA}' AND TABLE_NAME='{matched}'"
            )
            cols = {row[0] for row in cursor.fetchall()}
            _table_columns_cache[table_name] = cols
            # Also cache the matched name
            _table_columns_cache[matched] = cols
            return cols

        _table_columns_cache[table_name] = set()
        return set()
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
    """Validate all table and column references in a query against actual HANA catalog.

    Two-phase validation:
    1. Table names: fuzzy-match any table in FROM/JOIN/subselect that doesn't exist
    2. Column names: fuzzy-match any column in SELECT/WHERE that doesn't exist

    For columns that can't be matched, they are DROPPED from the SELECT clause
    (with a warning) rather than causing a query failure.
    """
    fixed_query = query

    # ---- Phase 1: Fix table names ----
    table_replacements = {}
    for match in _FROM_TABLE_RE.finditer(fixed_query):
        tname = match.group(1)
        all_tables = get_all_tables(cursor)
        if tname not in all_tables:
            matched = fuzzy_match_table(cursor, tname)
            if matched and matched != tname:
                table_replacements[f"{SCHEMA}.{tname}"] = f"{SCHEMA}.{matched}"
                logger.info(f"    Table fix: {tname} -> {matched}")
            else:
                logger.warning(f"    Table {tname} not found in {SCHEMA} schema")

    for old, new in table_replacements.items():
        fixed_query = fixed_query.replace(old, new)

    # ---- Phase 2: Fix column names ----
    # Re-extract table names after table fixes
    tables_in_query = _FROM_TABLE_RE.findall(fixed_query)
    if not tables_in_query:
        return fixed_query

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
    for match in alias_pattern.finditer(fixed_query):
        alias_map[match.group(2).upper()] = match.group(1)
    # Also map unaliased tables
    for tname in tables_in_query:
        alias_map[tname] = tname

    # Primary table is the first FROM
    primary_table = tables_in_query[0]

    col_replacements = {}
    cols_to_drop = []

    # Check each "alias.COLUMN" reference
    for match in _ALIAS_RE.finditer(fixed_query):
        alias, col = match.group(1).upper(), match.group(2)
        table = alias_map.get(alias)
        if not table or table not in table_cols:
            continue
        if col not in table_cols[table]:
            replacement = fuzzy_match_column(col, table_cols[table])
            if replacement and replacement != col:
                old_ref = f"{match.group(1)}.{col}"
                new_ref = f"{match.group(1)}.{replacement}"
                col_replacements[old_ref] = new_ref
                logger.info(f"    Column fix: {old_ref} -> {new_ref}")
            elif not replacement:
                old_ref = f"{match.group(1)}.{col}"
                cols_to_drop.append(old_ref)
                logger.warning(f"    Column {alias}.{col} not found in {table}, will drop from SELECT")

    # Check bare column references (no alias) against primary table
    select_match = _SELECT_COL_RE.search(fixed_query)
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
                    col_replacements[col_token] = replacement
                    logger.info(f"    Column fix: {col_token} -> {replacement} (in {primary_table})")
                elif not replacement:
                    cols_to_drop.append(col_token)
                    logger.warning(f"    Column {col_token} not found in {primary_table}, will drop from SELECT")

    # Apply column replacements
    for old, new in col_replacements.items():
        fixed_query = fixed_query.replace(old, new)

    # Drop unfixable columns from SELECT clause only
    if cols_to_drop:
        select_match = _SELECT_COL_RE.search(fixed_query)
        if select_match:
            original_select = select_match.group(1)
            fixed_select = original_select
            for col_ref in cols_to_drop:
                # Remove "col_ref," or ", col_ref" patterns from SELECT
                # Handle both "alias.COL," and ", alias.COL" and standalone
                for pattern in [
                    rf",\s*{re.escape(col_ref)}\b",  # ", alias.COL"
                    rf"\b{re.escape(col_ref)}\s*,",   # "alias.COL,"
                    rf"\b{re.escape(col_ref)}\b",      # standalone
                ]:
                    new_select = re.sub(pattern, "", fixed_select, flags=re.IGNORECASE)
                    if new_select != fixed_select:
                        fixed_select = new_select
                        break
            # Clean up any double commas or leading/trailing commas
            fixed_select = re.sub(r",\s*,", ",", fixed_select)
            fixed_select = re.sub(r"^\s*,\s*", "", fixed_select)
            fixed_select = re.sub(r"\s*,\s*$", "", fixed_select)
            fixed_query = fixed_query.replace(original_select, fixed_select)

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
