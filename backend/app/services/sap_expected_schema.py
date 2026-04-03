"""
SAP Expected Schema — Defines what SAP fields we need for each AWS SC DM entity.

Each entity specifies:
  - primary_table: The main SAP table
  - fields: Dict of aws_sc_field -> expected SAP mapping
    - sap_field: Expected SAP technical field name
    - table: Override table if field is in a different table (requires join)
    - join: Field used to join back to primary table
    - required: Whether the field is mandatory for the entity to be usable
    - description_keywords: Keywords to search in DD04T descriptions for fuzzy match
    - expected_values: Known value patterns for sample validation
    - fallback_tables: Alternative tables to check if not in primary
    - synonyms: Alternative SAP field names across releases
"""

from typing import Any, Dict

EXPECTED_SCHEMA: Dict[str, Dict[str, Any]] = {
    # =========================================================================
    # product — MARA / MAKT / MARC / MBEW / MARM
    # =========================================================================
    "product": {
        "primary_table": "MARA",
        "fields": {
            "product_id": {
                "sap_field": "MATNR",
                "required": True,
                "description_keywords": ["material number", "product number"],
            },
            "description": {
                "sap_field": "MAKTX",
                "table": "MAKT",
                "join": "MATNR",
                "join_filter": {"SPRAS": "E"},
                "description_keywords": ["material description", "product description"],
            },
            "product_type": {
                "sap_field": "MTART",
                "description_keywords": ["material type", "product type"],
            },
            "base_uom": {
                "sap_field": "MEINS",
                "required": True,
                "description_keywords": ["base unit of measure", "base UOM"],
            },
            "product_group": {
                "sap_field": "MATKL",
                "description_keywords": ["material group", "product group"],
            },
            "gross_weight": {
                "sap_field": "BRGEW",
                "description_keywords": ["gross weight"],
            },
            "net_weight": {
                "sap_field": "NTGEW",
                "description_keywords": ["net weight"],
            },
            "weight_uom": {
                "sap_field": "GEWEI",
                "description_keywords": ["weight unit"],
            },
            "volume": {
                "sap_field": "VOLUM",
                "description_keywords": ["volume"],
            },
            "volume_uom": {
                "sap_field": "VOLEH",
                "description_keywords": ["volume unit"],
            },
            "industry_sector": {
                "sap_field": "MBRSH",
                "description_keywords": ["industry sector"],
            },
            "deletion_flag": {
                "sap_field": "LVORM",
                "description_keywords": ["deletion flag", "marked for deletion"],
            },
            # MARC fields (plant-level material data)
            "mrp_type": {
                "sap_field": "DISMM",
                "table": "MARC",
                "join": "MATNR",
                "description_keywords": ["MRP type", "planning type"],
            },
            "procurement_type": {
                "sap_field": "BESKZ",
                "table": "MARC",
                "join": "MATNR",
                "description_keywords": ["procurement type", "special procurement"],
                "expected_values": ["E", "F", "X"],
            },
            "safety_stock": {
                "sap_field": "EISBE",
                "table": "MARC",
                "join": "MATNR",
                "description_keywords": ["safety stock"],
            },
            "planned_delivery_days": {
                "sap_field": "PLIFZ",
                "table": "MARC",
                "join": "MATNR",
                "description_keywords": ["planned delivery time", "lead time"],
            },
            "gr_processing_days": {
                "sap_field": "WEBAZ",
                "table": "MARC",
                "join": "MATNR",
                "description_keywords": ["goods receipt processing"],
            },
            "lot_size_procedure": {
                "sap_field": "DISLS",
                "table": "MARC",
                "join": "MATNR",
                "description_keywords": ["lot size", "lot sizing"],
            },
            "min_lot_size": {
                "sap_field": "BSTMI",
                "table": "MARC",
                "join": "MATNR",
                "description_keywords": ["minimum lot size"],
            },
            "max_lot_size": {
                "sap_field": "BSTMA",
                "table": "MARC",
                "join": "MATNR",
                "description_keywords": ["maximum lot size"],
            },
            "fixed_lot_size": {
                "sap_field": "BSTFE",
                "table": "MARC",
                "join": "MATNR",
                "description_keywords": ["fixed lot size"],
            },
            # MBEW fields (valuation)
            "standard_price": {
                "sap_field": "STPRS",
                "table": "MBEW",
                "join": "MATNR",
                "description_keywords": ["standard price"],
            },
            "moving_avg_price": {
                "sap_field": "VERPR",
                "table": "MBEW",
                "join": "MATNR",
                "description_keywords": ["moving average price"],
            },
            "price_control": {
                "sap_field": "VPRSV",
                "table": "MBEW",
                "join": "MATNR",
                "description_keywords": ["price control indicator"],
                "expected_values": ["S", "V"],
            },
        },
    },

    # =========================================================================
    # product_bom — STKO / STPO / MAST
    # =========================================================================
    "product_bom": {
        "primary_table": "STKO",
        "fields": {
            "bom_number": {
                "sap_field": "STLNR",
                "required": True,
                "description_keywords": ["bill of material number", "BOM number"],
            },
            "bom_alternative": {
                "sap_field": "STLAL",
                "required": True,
                "description_keywords": ["alternative BOM", "BOM alternative"],
            },
            "bom_usage_type": {
                "sap_field": "STLAN",
                "description_keywords": ["BOM usage", "BOM category", "application"],
                "expected_values": ["1", "2", "3", "5"],
                "fallback_tables": ["MAST"],
            },
            "header_quantity": {
                "sap_field": "BMENG",
                "description_keywords": ["base quantity", "header quantity"],
            },
            "header_uom": {
                "sap_field": "BMEIN",
                "description_keywords": ["BOM unit of measure", "header UOM"],
            },
            "bom_status": {
                "sap_field": "STLST",
                "description_keywords": ["BOM status"],
            },
            # Link to material via MAST
            "product_id": {
                "sap_field": "MATNR",
                "table": "MAST",
                "join": "STLNR",
                "required": True,
                "description_keywords": ["material number"],
            },
            "site_id": {
                "sap_field": "WERKS",
                "table": "MAST",
                "join": "STLNR",
                "description_keywords": ["plant"],
            },
            # Component items via STPO
            "component_product_id": {
                "sap_field": "IDNRK",
                "table": "STPO",
                "join": "STLNR",
                "required": True,
                "description_keywords": ["component material", "BOM component"],
            },
            "component_quantity": {
                "sap_field": "MENGE",
                "table": "STPO",
                "join": "STLNR",
                "description_keywords": ["component quantity", "item quantity"],
            },
            "component_uom": {
                "sap_field": "MEINS",
                "table": "STPO",
                "join": "STLNR",
                "description_keywords": ["component unit"],
            },
            "item_category": {
                "sap_field": "POSTP",
                "table": "STPO",
                "join": "STLNR",
                "description_keywords": ["item category", "BOM item category"],
            },
            "item_number": {
                "sap_field": "POSNR",
                "table": "STPO",
                "join": "STLNR",
                "description_keywords": ["item number"],
            },
            "scrap_pct": {
                "sap_field": "AUSCH",
                "table": "STPO",
                "join": "STLNR",
                "description_keywords": ["component scrap", "scrap percentage"],
            },
            "planning_proportion": {
                "sap_field": "ANTEI",
                "table": "STPO",
                "join": "STLNR",
                "description_keywords": ["usage probability", "planning proportion"],
            },
        },
    },

    # =========================================================================
    # site — T001W
    # =========================================================================
    "site": {
        "primary_table": "T001W",
        "fields": {
            "site_id": {
                "sap_field": "WERKS",
                "required": True,
                "description_keywords": ["plant", "site", "works"],
            },
            "name": {
                "sap_field": "NAME1",
                "required": True,
                "description_keywords": ["plant name", "name"],
            },
            "company_code": {
                "sap_field": "BUKRS",
                "description_keywords": ["company code"],
            },
            "factory_calendar": {
                "sap_field": "FABKL",
                "description_keywords": ["factory calendar"],
            },
            "street": {
                "sap_field": "STRAS",
                "description_keywords": ["street", "address"],
            },
            "city": {
                "sap_field": "ORT01",
                "description_keywords": ["city"],
            },
            "postal_code": {
                "sap_field": "PSTLZ",
                "description_keywords": ["postal code", "zip"],
            },
            "region": {
                "sap_field": "REGIO",
                "description_keywords": ["region", "state"],
            },
            "country": {
                "sap_field": "LAND1",
                "description_keywords": ["country"],
            },
        },
    },

    # =========================================================================
    # trading_partner — LFA1 (vendors) / KNA1 (customers)
    # =========================================================================
    "trading_partner": {
        "primary_table": "LFA1",
        "secondary_tables": ["KNA1"],
        "fields": {
            "vendor_id": {
                "sap_field": "LIFNR",
                "required": True,
                "description_keywords": ["vendor number", "supplier number", "account number"],
            },
            "name": {
                "sap_field": "NAME1",
                "required": True,
                "description_keywords": ["name", "vendor name"],
            },
            "country": {
                "sap_field": "LAND1",
                "description_keywords": ["country"],
            },
            "city": {
                "sap_field": "ORT01",
                "description_keywords": ["city"],
            },
            "postal_code": {
                "sap_field": "PSTLZ",
                "description_keywords": ["postal code"],
            },
            "street": {
                "sap_field": "STRAS",
                "description_keywords": ["street"],
            },
            "region": {
                "sap_field": "REGIO",
                "description_keywords": ["region"],
            },
            # KNA1 customer fields
            "customer_id": {
                "sap_field": "KUNNR",
                "table": "KNA1",
                "required": True,
                "description_keywords": ["customer number"],
            },
        },
    },

    # =========================================================================
    # transportation_lane — EORD (source list) / EINE (info records)
    # =========================================================================
    "transportation_lane": {
        "primary_table": "EORD",
        "fields": {
            "product_id": {
                "sap_field": "MATNR",
                "required": True,
                "description_keywords": ["material number"],
            },
            "destination_site_id": {
                "sap_field": "WERKS",
                "required": True,
                "description_keywords": ["plant"],
            },
            "source_partner_id": {
                "sap_field": "LIFNR",
                "required": True,
                "description_keywords": ["vendor", "supplier", "source"],
            },
            "valid_from": {
                "sap_field": "VDATU",
                "description_keywords": ["valid from", "validity start"],
            },
            "valid_to": {
                "sap_field": "BDATU",
                "description_keywords": ["valid to", "validity end"],
            },
            "fixed_vendor": {
                "sap_field": "FLIFN",
                "description_keywords": ["fixed vendor", "fixed source"],
            },
            "priority": {
                "sap_field": "NOTKZ",
                "description_keywords": ["priority", "indicator"],
            },
            "purchasing_org": {
                "sap_field": "EKORG",
                "description_keywords": ["purchasing organization"],
            },
            # Lead time from info record
            "lead_time_days": {
                "sap_field": "APLFZ",
                "table": "EINE",
                "join": "LIFNR",
                "description_keywords": ["planned delivery time", "lead time"],
            },
            "net_price": {
                "sap_field": "NETPR",
                "table": "EINE",
                "join": "LIFNR",
                "description_keywords": ["net price"],
            },
            "min_order_qty": {
                "sap_field": "MINBM",
                "table": "EINE",
                "join": "LIFNR",
                "description_keywords": ["minimum order", "minimum quantity"],
            },
            "standard_order_qty": {
                "sap_field": "NORBM",
                "table": "EINE",
                "join": "LIFNR",
                "description_keywords": ["standard order quantity", "normal order"],
            },
        },
    },

    # =========================================================================
    # purchase_order — EKKO (header) / EKPO (items) / EKET (schedule lines)
    # =========================================================================
    "purchase_order": {
        "primary_table": "EKKO",
        "fields": {
            "po_number": {
                "sap_field": "EBELN",
                "required": True,
                "description_keywords": ["purchase order number", "purchasing document"],
            },
            "po_type": {
                "sap_field": "BSART",
                "description_keywords": ["order type", "document type"],
            },
            "vendor_id": {
                "sap_field": "LIFNR",
                "required": True,
                "description_keywords": ["vendor", "supplier"],
            },
            "company_code": {
                "sap_field": "BUKRS",
                "description_keywords": ["company code"],
            },
            "purchasing_org": {
                "sap_field": "EKORG",
                "description_keywords": ["purchasing organization"],
            },
            "purchasing_group": {
                "sap_field": "EKGRP",
                "description_keywords": ["purchasing group"],
            },
            "order_date": {
                "sap_field": "BEDAT",
                "required": True,
                "description_keywords": ["purchase order date", "order date"],
            },
            "creation_date": {
                "sap_field": "AEDAT",
                "description_keywords": ["creation date", "created on"],
            },
            "currency": {
                "sap_field": "WAERS",
                "description_keywords": ["currency", "document currency"],
            },
            # EKPO item fields
            "item_number": {
                "sap_field": "EBELP",
                "table": "EKPO",
                "join": "EBELN",
                "required": True,
                "description_keywords": ["item number", "line item"],
            },
            "product_id": {
                "sap_field": "MATNR",
                "table": "EKPO",
                "join": "EBELN",
                "required": True,
                "description_keywords": ["material number"],
            },
            "site_id": {
                "sap_field": "WERKS",
                "table": "EKPO",
                "join": "EBELN",
                "description_keywords": ["plant"],
            },
            "order_quantity": {
                "sap_field": "MENGE",
                "table": "EKPO",
                "join": "EBELN",
                "required": True,
                "description_keywords": ["order quantity", "PO quantity"],
            },
            "order_uom": {
                "sap_field": "MEINS",
                "table": "EKPO",
                "join": "EBELN",
                "description_keywords": ["order unit"],
            },
            "net_price": {
                "sap_field": "NETPR",
                "table": "EKPO",
                "join": "EBELN",
                "description_keywords": ["net price"],
            },
            "delivery_complete": {
                "sap_field": "ELIKZ",
                "table": "EKPO",
                "join": "EBELN",
                "description_keywords": ["delivery completed", "final delivery"],
            },
            # EKET schedule line fields
            "schedule_line": {
                "sap_field": "ETENR",
                "table": "EKET",
                "join": "EBELN",
                "description_keywords": ["schedule line", "delivery schedule"],
            },
            "delivery_date": {
                "sap_field": "EINDT",
                "table": "EKET",
                "join": "EBELN",
                "description_keywords": ["delivery date", "item delivery date"],
            },
            "scheduled_qty": {
                "sap_field": "MENGE",
                "table": "EKET",
                "join": "EBELN",
                "description_keywords": ["scheduled quantity"],
            },
            "received_qty": {
                "sap_field": "WEMNG",
                "table": "EKET",
                "join": "EBELN",
                "description_keywords": ["goods received", "quantity delivered"],
            },
        },
    },

    # =========================================================================
    # inv_level — MARD (storage location stock)
    # =========================================================================
    "inv_level": {
        "primary_table": "MARD",
        "fields": {
            "product_id": {
                "sap_field": "MATNR",
                "required": True,
                "description_keywords": ["material number"],
            },
            "site_id": {
                "sap_field": "WERKS",
                "required": True,
                "description_keywords": ["plant"],
            },
            "storage_location": {
                "sap_field": "LGORT",
                "description_keywords": ["storage location"],
            },
            "unrestricted_stock": {
                "sap_field": "LABST",
                "required": True,
                "description_keywords": [
                    "unrestricted", "valuated stock", "warehouse stock",
                ],
            },
        },
    },

    # =========================================================================
    # inv_policy — MARC (MRP settings for the material-plant)
    # =========================================================================
    "inv_policy": {
        "primary_table": "MARC",
        "fields": {
            "product_id": {
                "sap_field": "MATNR",
                "required": True,
                "description_keywords": ["material number"],
            },
            "site_id": {
                "sap_field": "WERKS",
                "required": True,
                "description_keywords": ["plant"],
            },
            "mrp_type": {
                "sap_field": "DISMM",
                "required": True,
                "description_keywords": ["MRP type", "planning type"],
            },
            "mrp_controller": {
                "sap_field": "DISPO",
                "description_keywords": ["MRP controller"],
            },
            "reorder_point": {
                "sap_field": "MINBE",
                "description_keywords": ["reorder point", "reorder threshold"],
                "synonyms": ["MINBE"],
            },
            "safety_stock": {
                "sap_field": "EISBE",
                "required": True,
                "description_keywords": ["safety stock"],
            },
            "lot_size_procedure": {
                "sap_field": "DISLS",
                "description_keywords": ["lot size", "lot sizing procedure"],
            },
            "min_lot_size": {
                "sap_field": "BSTMI",
                "description_keywords": ["minimum lot size"],
            },
            "max_lot_size": {
                "sap_field": "BSTMA",
                "description_keywords": ["maximum lot size"],
            },
            "fixed_lot_size": {
                "sap_field": "BSTFE",
                "description_keywords": ["fixed lot size"],
            },
            "planned_delivery_days": {
                "sap_field": "PLIFZ",
                "description_keywords": ["planned delivery time"],
            },
            "gr_processing_days": {
                "sap_field": "WEBAZ",
                "description_keywords": ["goods receipt processing"],
            },
            "procurement_type": {
                "sap_field": "BESKZ",
                "description_keywords": ["procurement type"],
                "expected_values": ["E", "F", "X"],
            },
            "special_procurement": {
                "sap_field": "SOBSL",
                "description_keywords": ["special procurement"],
            },
            "scrap_pct": {
                "sap_field": "AUSSS",
                "description_keywords": ["assembly scrap", "scrap percentage"],
            },
        },
    },

    # =========================================================================
    # sales_order — VBAK (header) / VBAP (items) / VBEP (schedule lines)
    # =========================================================================
    "sales_order": {
        "primary_table": "VBAK",
        "fields": {
            "sales_order": {
                "sap_field": "VBELN",
                "required": True,
                "description_keywords": ["sales document", "sales order number"],
            },
            "order_type": {
                "sap_field": "AUART",
                "description_keywords": ["sales document type", "order type"],
            },
            "sales_org": {
                "sap_field": "VKORG",
                "description_keywords": ["sales organization"],
            },
            "distribution_channel": {
                "sap_field": "VTWEG",
                "description_keywords": ["distribution channel"],
            },
            "division": {
                "sap_field": "SPART",
                "description_keywords": ["division"],
            },
            "sold_to_party": {
                "sap_field": "KUNNR",
                "required": True,
                "description_keywords": ["sold-to party", "customer number"],
            },
            "order_date": {
                "sap_field": "ERDAT",
                "required": True,
                "description_keywords": ["creation date", "order date"],
            },
            # VBAP item fields
            "item_number": {
                "sap_field": "POSNR",
                "table": "VBAP",
                "join": "VBELN",
                "description_keywords": ["item number"],
            },
            "product_id": {
                "sap_field": "MATNR",
                "table": "VBAP",
                "join": "VBELN",
                "required": True,
                "description_keywords": ["material number"],
            },
            "site_id": {
                "sap_field": "WERKS",
                "table": "VBAP",
                "join": "VBELN",
                "description_keywords": ["plant", "delivering plant"],
            },
            "requested_qty": {
                "sap_field": "KWMENG",
                "table": "VBAP",
                "join": "VBELN",
                "description_keywords": ["order quantity", "cumulative order"],
            },
            "sales_uom": {
                "sap_field": "VRKME",
                "table": "VBAP",
                "join": "VBELN",
                "description_keywords": ["sales unit"],
            },
            "net_value": {
                "sap_field": "NETPR",
                "table": "VBAP",
                "join": "VBELN",
                "description_keywords": ["net price", "net value"],
            },
        },
    },

    # =========================================================================
    # production_order — AFKO / AFPO
    # =========================================================================
    "production_order": {
        "primary_table": "AFKO",
        "fields": {
            "order_number": {
                "sap_field": "AUFNR",
                "required": True,
                "description_keywords": ["order number", "production order"],
            },
            "order_type": {
                "sap_field": "AUART",
                "description_keywords": ["order type"],
            },
            "product_id": {
                "sap_field": "MATNR",
                "required": True,
                "description_keywords": ["material number"],
            },
            "site_id": {
                "sap_field": "WERKS",
                "required": True,
                "description_keywords": ["plant", "production plant"],
            },
            "planned_qty": {
                "sap_field": "GAMNG",
                "required": True,
                "description_keywords": ["total order quantity", "planned quantity"],
            },
            "confirmed_qty": {
                "sap_field": "WEMNG",
                "description_keywords": ["delivered quantity", "goods receipt"],
            },
            "planned_start": {
                "sap_field": "GSTRP",
                "description_keywords": ["basic start date", "planned start"],
            },
            "planned_end": {
                "sap_field": "GLTRP",
                "description_keywords": ["basic finish date", "planned end"],
            },
            "release_date": {
                "sap_field": "FTRMI",
                "description_keywords": ["actual release date", "release date"],
            },
            "status": {
                "sap_field": "STAT",
                "description_keywords": ["system status", "order status"],
            },
        },
    },

    # =========================================================================
    # delivery — LIKP (header) / LIPS (items)
    # =========================================================================
    "delivery": {
        "primary_table": "LIKP",
        "fields": {
            "delivery_number": {
                "sap_field": "VBELN",
                "required": True,
                "description_keywords": ["delivery number", "delivery document"],
            },
            "delivery_type": {
                "sap_field": "LFART",
                "description_keywords": ["delivery type"],
            },
            "ship_to_party": {
                "sap_field": "KUNNR",
                "description_keywords": ["ship-to party", "customer"],
            },
            "shipping_point": {
                "sap_field": "VSTEL",
                "description_keywords": ["shipping point"],
            },
            "planned_gi_date": {
                "sap_field": "WADAT",
                "description_keywords": ["planned goods issue date"],
            },
            "actual_gi_date": {
                "sap_field": "WADAT_IST",
                "description_keywords": ["actual goods movement date", "actual GI"],
            },
            # LIPS item fields
            "item_number": {
                "sap_field": "POSNR",
                "table": "LIPS",
                "join": "VBELN",
                "description_keywords": ["delivery item"],
            },
            "product_id": {
                "sap_field": "MATNR",
                "table": "LIPS",
                "join": "VBELN",
                "required": True,
                "description_keywords": ["material number"],
            },
            "site_id": {
                "sap_field": "WERKS",
                "table": "LIPS",
                "join": "VBELN",
                "description_keywords": ["plant"],
            },
            "delivery_qty": {
                "sap_field": "LFIMG",
                "table": "LIPS",
                "join": "VBELN",
                "required": True,
                "description_keywords": ["actual delivery quantity", "delivery quantity"],
            },
            "delivery_uom": {
                "sap_field": "VRKME",
                "table": "LIPS",
                "join": "VBELN",
                "description_keywords": ["sales unit"],
            },
            "ref_document": {
                "sap_field": "VGBEL",
                "table": "LIPS",
                "join": "VBELN",
                "description_keywords": ["reference document", "preceding document"],
            },
        },
    },

    # =========================================================================
    # material_movement — MKPF (header) / MSEG (items)
    # =========================================================================
    "material_movement": {
        "primary_table": "MKPF",
        "fields": {
            "document_number": {
                "sap_field": "MBLNR",
                "required": True,
                "description_keywords": ["material document", "document number"],
            },
            "document_year": {
                "sap_field": "MJAHR",
                "required": True,
                "description_keywords": ["material document year"],
            },
            "posting_date": {
                "sap_field": "BUDAT",
                "required": True,
                "description_keywords": ["posting date"],
            },
            "movement_type": {
                "sap_field": "BWART",
                "description_keywords": ["movement type"],
            },
            # MSEG item fields
            "product_id": {
                "sap_field": "MATNR",
                "table": "MSEG",
                "join": "MBLNR",
                "required": True,
                "description_keywords": ["material number"],
            },
            "site_id": {
                "sap_field": "WERKS",
                "table": "MSEG",
                "join": "MBLNR",
                "description_keywords": ["plant"],
            },
            "storage_location": {
                "sap_field": "LGORT",
                "table": "MSEG",
                "join": "MBLNR",
                "description_keywords": ["storage location"],
            },
            "quantity": {
                "sap_field": "MENGE",
                "table": "MSEG",
                "join": "MBLNR",
                "required": True,
                "description_keywords": ["quantity"],
            },
            "uom": {
                "sap_field": "MEINS",
                "table": "MSEG",
                "join": "MBLNR",
                "description_keywords": ["base unit"],
            },
            "debit_credit": {
                "sap_field": "SHKZG",
                "table": "MSEG",
                "join": "MBLNR",
                "description_keywords": ["debit/credit", "debit credit indicator"],
            },
        },
    },
}


def get_all_required_tables() -> set:
    """Return the set of all SAP tables referenced in the expected schema."""
    tables = set()
    for entity_def in EXPECTED_SCHEMA.values():
        tables.add(entity_def["primary_table"])
        for sec in entity_def.get("secondary_tables", []):
            tables.add(sec)
        for field_def in entity_def["fields"].values():
            if "table" in field_def:
                tables.add(field_def["table"])
            for fb in field_def.get("fallback_tables", []):
                tables.add(fb)
    return tables


def get_required_fields_for_entity(entity_name: str) -> list:
    """Return list of field names marked as required for an entity."""
    entity = EXPECTED_SCHEMA.get(entity_name, {})
    return [
        fname for fname, fdef in entity.get("fields", {}).items()
        if fdef.get("required")
    ]
