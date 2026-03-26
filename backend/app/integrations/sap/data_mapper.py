"""
Supply Chain Data Model Mapper.

Maps SAP S/4HANA and APO data to Supply Chain Data Model entities:
- Sites (locations, plants, warehouses)
- Products (materials, SKUs)
- Inventory Levels
- Supply Plans
- Demand Plans
- Purchase Orders
- Sales Orders
- Shipments

Reference: Supply Chain Data Model v1.0
https://docs.[removed]
"""

import logging
import math
from typing import Dict, List, Optional, Any
from datetime import datetime
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def _safe_col(df: pd.DataFrame, name: str, default="") -> pd.Series:
    """Get column from DataFrame, returning a Series filled with default if missing.

    Avoids the broken pattern ``df.get("COL", scalar).astype(...)`` which fails
    when the column is absent because ``df.get`` returns the scalar default,
    not a Series.
    """
    if name in df.columns:
        return df[name]
    return pd.Series(default, index=df.index)


class SupplyChainMapper:
    """
    Maps SAP data to Supply Chain Data Model format.

    Supply Chain Core Entities:
    1. Sites - Physical locations in the supply chain
    2. Products - Materials/SKUs
    3. InventoryLevel - Current inventory status
    4. SupplyPlan - Planned inbound supply
    5. DemandPlan - Forecasted demand
    6. PurchaseOrder - Procurement orders
    7. SalesOrder - Customer orders
    8. Shipment - Deliveries/shipments
    """

    # Supply Chain Data Model required fields
    SITE_SCHEMA = {
        "site_id": str,
        "site_name": str,
        "site_type": str,  # PLANT, DC, WAREHOUSE, CUSTOMER, SUPPLIER
        "address": str,
        "city": str,
        "state": str,
        "country": str,
        "postal_code": str,
        "latitude": float,
        "longitude": float,
        "time_zone": str,
        "is_active": bool,
    }

    PRODUCT_SCHEMA = {
        "product_id": str,
        "product_name": str,
        "product_description": str,
        "product_category": str,
        "unit_of_measure": str,
        "weight": float,
        "weight_unit": str,
        "volume": float,
        "volume_unit": str,
        "is_active": bool,
    }

    INVENTORY_LEVEL_SCHEMA = {
        "site_id": str,
        "product_id": str,
        "inventory_date": datetime,
        "available_quantity": float,
        "in_transit_quantity": float,
        "reserved_quantity": float,
        "safety_stock_quantity": float,
        "unit_of_measure": str,
    }

    SUPPLY_PLAN_SCHEMA = {
        "site_id": str,
        "product_id": str,
        "plan_date": datetime,
        "planned_quantity": float,
        "unit_of_measure": str,
        "source_type": str,  # PRODUCTION, PURCHASE, TRANSFER
        "source_site_id": str,
        "lead_time_days": int,
    }

    DEMAND_PLAN_SCHEMA = {
        "site_id": str,
        "product_id": str,
        "plan_date": datetime,
        "forecasted_quantity": float,
        "unit_of_measure": str,
        "forecast_type": str,  # SALES, CONSUMPTION, TRANSFER
        "confidence_level": float,
    }

    PURCHASE_ORDER_SCHEMA = {
        "po_number": str,
        "po_line_number": str,
        "supplier_id": str,
        "product_id": str,
        "destination_site_id": str,
        "order_date": datetime,
        "requested_delivery_date": datetime,
        "order_quantity": float,
        "open_quantity": float,
        "unit_of_measure": str,
        "unit_price": float,
        "currency": str,
        "status": str,
    }

    SALES_ORDER_SCHEMA = {
        "so_number": str,
        "so_line_number": str,
        "customer_id": str,
        "product_id": str,
        "source_site_id": str,
        "order_date": datetime,
        "requested_delivery_date": datetime,
        "order_quantity": float,
        "open_quantity": float,
        "unit_of_measure": str,
        "unit_price": float,
        "currency": str,
        "status": str,
    }

    SHIPMENT_SCHEMA = {
        "shipment_id": str,
        "shipment_line_number": str,
        "product_id": str,
        "source_site_id": str,
        "destination_site_id": str,
        "shipment_date": datetime,
        "expected_delivery_date": datetime,
        "actual_delivery_date": datetime,
        "shipped_quantity": float,
        "unit_of_measure": str,
        "shipment_type": str,  # INBOUND, OUTBOUND, TRANSFER
        "status": str,
    }

    def map_s4hana_plants_to_sites(self, plants_df: pd.DataFrame) -> pd.DataFrame:
        """
        Map S/4HANA plants (T001W) to Supply Chain Sites.

        Args:
            plants_df: DataFrame from S4HANAConnector.extract_plants()

        Returns:
            DataFrame in AWS Sites schema
        """
        logger.info("Mapping S/4HANA plants to AWS Sites")

        sites = pd.DataFrame()

        # Map fields
        sites["site_id"] = plants_df["WERKS"]
        sites["site_name"] = plants_df.get("NAME1", "")
        sites["site_type"] = "PLANT"  # S/4HANA plants are typically production sites
        sites["address"] = _safe_col(plants_df, "STRAS", "").astype(str).str.strip()
        sites["city"] = _safe_col(plants_df, "ORT01", "").astype(str).str.strip()
        sites["state"] = _safe_col(plants_df, "REGIO", "").astype(str).str.strip()
        sites["country"] = _safe_col(plants_df, "LAND1", "").astype(str).str.strip()
        sites["postal_code"] = _safe_col(plants_df, "PSTLZ", "").astype(str).str.strip()
        sites["latitude"] = np.nan  # Populated by geocoding service
        sites["longitude"] = np.nan
        sites["time_zone"] = "UTC"
        sites["is_active"] = True

        logger.info(f"Mapped {len(sites)} plants to Sites")
        return sites

    def map_apo_locations_to_sites(self, locations_df: pd.DataFrame) -> pd.DataFrame:
        """
        Map APO locations to Supply Chain Sites.

        Args:
            locations_df: DataFrame from APOConnector.extract_locations()

        Returns:
            DataFrame in AWS Sites schema
        """
        logger.info("Mapping APO locations to AWS Sites")

        sites = pd.DataFrame()

        # Map fields
        sites["site_id"] = locations_df["LOCNO"]
        sites["site_name"] = locations_df.get("LOCDESC", "")
        sites["site_type"] = _safe_col(locations_df, "LOCTYPE", "WAREHOUSE").str.upper()
        sites["address"] = ""
        sites["city"] = locations_df.get("CITY", "")
        sites["state"] = locations_df.get("REGION", "")
        sites["country"] = locations_df.get("COUNTRY", "")
        sites["postal_code"] = ""
        sites["latitude"] = np.nan
        sites["longitude"] = np.nan
        sites["time_zone"] = "UTC"
        sites["is_active"] = True

        logger.info(f"Mapped {len(sites)} APO locations to Sites")
        return sites

    def map_s4hana_materials_to_products(
        self,
        materials_df: pd.DataFrame,
        mbew_df: pd.DataFrame = None,
    ) -> pd.DataFrame:
        """
        Map S/4HANA materials to Supply Chain Products.

        Args:
            materials_df: DataFrame from MARA (+MAKT descriptions)
            mbew_df: Optional MBEW material valuation for unit_cost

        Returns:
            DataFrame in AWS Products schema
        """
        logger.info("Mapping S/4HANA materials to AWS Products")

        products = pd.DataFrame()

        products["product_id"] = materials_df["MATNR"].astype(str).str.strip()
        products["product_name"] = _safe_col(materials_df, "MAKTX", "").where(
            _safe_col(materials_df, "MAKTX", "") != "", materials_df["MATNR"]
        )
        products["product_description"] = _safe_col(materials_df, "MAKTX", "")
        products["product_category"] = _safe_col(materials_df, "MATKL", "")
        products["unit_of_measure"] = _safe_col(materials_df, "MEINS", "EA")
        products["weight"] = pd.to_numeric(_safe_col(materials_df, "NTGEW", 0), errors="coerce")
        products["weight_unit"] = _safe_col(materials_df, "GEWEI", "KG")
        products["volume"] = pd.to_numeric(_safe_col(materials_df, "VOLUM", 0), errors="coerce")
        products["volume_unit"] = _safe_col(materials_df, "VOLEH", "M3")
        products["is_active"] = ~_safe_col(materials_df, "LVORM", "").astype(bool)

        # Product type from MTART: FERT=finished, HALB=semi, ROH=raw, HAWA=trading
        mtart_map = {"FERT": "finished", "HALB": "semi_finished", "ROH": "raw",
                     "HAWA": "trading", "VERP": "packaging", "NLAG": "non_stock"}
        products["product_type"] = _safe_col(materials_df, "MTART", "").map(mtart_map).fillna("standard")

        # Decode PRDHA → 3-level product hierarchy (5+5+8 character structure)
        prdha = _safe_col(materials_df, "PRDHA", "").astype(str).str.strip()
        products["category"] = prdha.str[:5].str.strip()
        products["family"] = prdha.str[5:10].str.strip()
        products["product_group"] = prdha.str[10:18].str.strip()
        products["product_group_id"] = prdha  # Full hierarchy key

        # Unit cost from MBEW (material valuation)
        if mbew_df is not None and not mbew_df.empty:
            mbew = mbew_df.copy()
            mbew["MATNR"] = mbew["MATNR"].astype(str).str.strip()
            # Use moving average price (VERPR) if price control V, else standard (STPRS)
            mbew["_unit_cost"] = pd.to_numeric(_safe_col(mbew, "VERPR", 0), errors="coerce")
            stprs = pd.to_numeric(_safe_col(mbew, "STPRS", 0), errors="coerce")
            peinh = pd.to_numeric(_safe_col(mbew, "PEINH", 1), errors="coerce").replace(0, 1)
            mbew["_unit_cost"] = mbew["_unit_cost"].where(mbew["_unit_cost"] > 0, stprs) / peinh
            # Standard price as selling price proxy (STPRS)
            mbew["_unit_price"] = stprs / peinh
            # Take first valuation per material (dedup across valuation areas)
            mbew_dedup = mbew.drop_duplicates(subset=["MATNR"], keep="first")
            cost_map = mbew_dedup.set_index("MATNR")["_unit_cost"]
            price_map = mbew_dedup.set_index("MATNR")["_unit_price"]
            products["unit_cost"] = products["product_id"].map(cost_map)
            products["unit_price"] = products["product_id"].map(price_map)
        else:
            products["unit_cost"] = np.nan
            products["unit_price"] = np.nan

        products["source"] = "SAP_MARA"

        logger.info(f"Mapped {len(products)} materials to Products")
        return products

    def map_apo_materials_to_products(self, materials_df: pd.DataFrame) -> pd.DataFrame:
        """
        Map APO materials to Supply Chain Products.

        Args:
            materials_df: DataFrame from APOConnector.extract_materials()

        Returns:
            DataFrame in AWS Products schema
        """
        logger.info("Mapping APO materials to AWS Products")

        products = pd.DataFrame()

        products["product_id"] = materials_df["MATNR"]
        products["product_name"] = materials_df.get("MATDESC", materials_df["MATNR"])
        products["product_description"] = materials_df.get("MATDESC", "")
        products["product_category"] = materials_df.get("PRODGRP", "")
        products["unit_of_measure"] = materials_df.get("BASEUNIT", "EA")
        products["weight"] = np.nan
        products["weight_unit"] = "KG"
        products["volume"] = np.nan
        products["volume_unit"] = "M3"
        products["is_active"] = materials_df.get("LIFCYCLE", "") != "OBSOLETE"

        logger.info(f"Mapped {len(products)} APO materials to Products")
        return products

    def map_s4hana_inventory_to_inventory_levels(
        self,
        inventory_df: pd.DataFrame,
        marc_df: pd.DataFrame = None,
        ekpo_df: pd.DataFrame = None,
    ) -> pd.DataFrame:
        """
        Map S/4HANA inventory (MARD) to AWS InventoryLevel.

        Enriches with:
        - MARC.EISBE → safety_stock_qty
        - EKPO open qty → on_order_qty (calculated: PO ordered - received)
        - MARD.SPEME → blocked/restricted stock (added to reserved)
        """
        logger.info("Mapping S/4HANA inventory to AWS InventoryLevel")

        inv_levels = pd.DataFrame()

        inv_levels["site_id"] = inventory_df["WERKS"].astype(str).str.strip()
        inv_levels["product_id"] = inventory_df["MATNR"].astype(str).str.strip()
        inv_levels["inventory_date"] = datetime.now()
        inv_levels["available_quantity"] = pd.to_numeric(
            _safe_col(inventory_df, "LABST", 0), errors="coerce"
        )
        inv_levels["in_transit_quantity"] = pd.to_numeric(
            _safe_col(inventory_df, "UMLME", 0), errors="coerce"
        )
        # Reserved = inspection stock + blocked stock
        insme = pd.to_numeric(_safe_col(inventory_df, "INSME", 0), errors="coerce").fillna(0)
        speme = pd.to_numeric(_safe_col(inventory_df, "SPEME", 0), errors="coerce").fillna(0)
        inv_levels["reserved_quantity"] = insme + speme

        # Safety stock from MARC.EISBE
        if marc_df is not None and not marc_df.empty and "EISBE" in marc_df.columns:
            ss_map = marc_df[["MATNR", "WERKS", "EISBE"]].copy()
            ss_map["MATNR"] = ss_map["MATNR"].astype(str).str.strip()
            ss_map["WERKS"] = ss_map["WERKS"].astype(str).str.strip()
            ss_map["_ss"] = pd.to_numeric(ss_map["EISBE"], errors="coerce").fillna(0)
            ss_map["_key"] = ss_map["MATNR"] + "|" + ss_map["WERKS"]
            ss_dict = ss_map.drop_duplicates(subset=["_key"]).set_index("_key")["_ss"].to_dict()
            inv_levels["safety_stock_quantity"] = (
                inv_levels["product_id"] + "|" + inv_levels["site_id"]
            ).map(ss_dict).fillna(0)
        else:
            inv_levels["safety_stock_quantity"] = 0.0

        # On-order quantity from open POs (EKPO.MENGE where not fully delivered)
        if ekpo_df is not None and not ekpo_df.empty:
            po_open = ekpo_df.copy()
            po_open["MATNR"] = po_open["MATNR"].astype(str).str.strip()
            po_open["WERKS"] = _safe_col(po_open, "WERKS", "").astype(str).str.strip()
            po_open["_open"] = pd.to_numeric(_safe_col(po_open, "MENGE", 0), errors="coerce").fillna(0)
            # Exclude deleted items
            if "LOEKZ" in po_open.columns:
                po_open = po_open[po_open["LOEKZ"].isna() | (po_open["LOEKZ"] == "")]
            on_order = po_open.groupby(["MATNR", "WERKS"])["_open"].sum().reset_index()
            on_order["_key"] = on_order["MATNR"] + "|" + on_order["WERKS"]
            oo_dict = on_order.set_index("_key")["_open"].to_dict()
            inv_levels["on_order_qty"] = (
                inv_levels["product_id"] + "|" + inv_levels["site_id"]
            ).map(oo_dict).fillna(0)
        else:
            inv_levels["on_order_qty"] = 0.0

        inv_levels["unit_of_measure"] = "EA"

        logger.info(f"Mapped {len(inv_levels)} inventory records to InventoryLevel")
        return inv_levels

    def map_apo_stock_to_inventory_levels(self, stock_df: pd.DataFrame) -> pd.DataFrame:
        """
        Map APO stock to AWS InventoryLevel.

        Args:
            stock_df: DataFrame from APOConnector.extract_stock()

        Returns:
            DataFrame in AWS InventoryLevel schema
        """
        logger.info("Mapping APO stock to AWS InventoryLevel")

        inv_levels = pd.DataFrame()

        inv_levels["site_id"] = stock_df["LOCNO"]
        inv_levels["product_id"] = stock_df["MATNR"]
        inv_levels["inventory_date"] = pd.to_datetime(
            stock_df.get("STOCK_DATE", datetime.now())
        )
        inv_levels["available_quantity"] = pd.to_numeric(
            stock_df.get("AVAILABLE_QTY", 0), errors="coerce"
        )
        inv_levels["in_transit_quantity"] = pd.to_numeric(
            stock_df.get("IN_TRANSIT_QTY", 0), errors="coerce"
        )
        inv_levels["reserved_quantity"] = pd.to_numeric(
            stock_df.get("BLOCKED_QTY", 0), errors="coerce"
        )
        inv_levels["safety_stock_quantity"] = 0.0  # Would come from material-location
        inv_levels["unit_of_measure"] = "EA"

        logger.info(f"Mapped {len(inv_levels)} APO stock records to InventoryLevel")
        return inv_levels

    def map_s4hana_po_to_purchase_orders(
        self,
        po_headers: pd.DataFrame,
        po_items: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Map S/4HANA purchase orders (EKKO/EKPO) to AWS PurchaseOrder.

        Args:
            po_headers: EKKO header data
            po_items: EKPO item data

        Returns:
            DataFrame in AWS PurchaseOrder schema
        """
        logger.info("Mapping S/4HANA POs to AWS PurchaseOrder")

        # Merge headers and items
        pos = po_items.merge(
            po_headers[["EBELN", "LIFNR", "BEDAT"]],
            on="EBELN",
            how="left"
        )

        po_orders = pd.DataFrame()

        po_orders["po_number"] = pos["EBELN"]
        po_orders["po_line_number"] = pos["EBELP"]
        po_orders["supplier_id"] = pos["LIFNR"]
        po_orders["product_id"] = pos["MATNR"]
        po_orders["destination_site_id"] = pos["WERKS"]
        po_orders["order_date"] = pd.to_datetime(pos["BEDAT"], errors="coerce")
        po_orders["requested_delivery_date"] = pd.NaT  # Would come from EKET
        po_orders["order_quantity"] = pd.to_numeric(pos["MENGE"], errors="coerce")
        po_orders["open_quantity"] = pd.to_numeric(pos["MENGE"], errors="coerce")  # Simplified
        po_orders["unit_of_measure"] = pos.get("MEINS", "EA")
        po_orders["unit_price"] = pd.to_numeric(pos.get("NETPR", 0), errors="coerce")
        po_orders["currency"] = "USD"  # Would need currency mapping
        po_orders["status"] = "OPEN"  # Simplified

        logger.info(f"Mapped {len(po_orders)} PO lines to PurchaseOrder")
        return po_orders

    def map_apo_orders_to_supply_plans(self, orders_df: pd.DataFrame) -> pd.DataFrame:
        """
        Map APO orders to AWS SupplyPlan.

        Args:
            orders_df: DataFrame from APOConnector.extract_orders()

        Returns:
            DataFrame in AWS SupplyPlan schema
        """
        logger.info("Mapping APO orders to AWS SupplyPlan")

        # Filter to supply-type orders (PO, TO inbound)
        supply_orders = orders_df[
            orders_df.get("ORDERTYPE", "").isin(["PO", "TO", "PR"])
        ].copy()

        supply_plan = pd.DataFrame()

        supply_plan["site_id"] = supply_orders.get("TO_LOC", "")
        supply_plan["product_id"] = supply_orders["MATNR"]
        supply_plan["plan_date"] = pd.to_datetime(
            supply_orders.get("DELIVERY_DATE", datetime.now()), errors="coerce"
        )
        supply_plan["planned_quantity"] = pd.to_numeric(
            supply_orders.get("OPEN_QTY", 0), errors="coerce"
        )
        supply_plan["unit_of_measure"] = "EA"

        # Map order type to source type
        supply_plan["source_type"] = _safe_col(supply_orders, "ORDERTYPE", "").map({
            "PO": "PURCHASE",
            "TO": "TRANSFER",
            "PR": "PRODUCTION"
        })

        supply_plan["source_site_id"] = supply_orders.get("FROM_LOC", "")
        supply_plan["lead_time_days"] = 0  # Would calculate from order/delivery dates

        logger.info(f"Mapped {len(supply_plan)} APO orders to SupplyPlan")
        return supply_plan

    def map_apo_snp_to_demand_plans(self, snp_df: pd.DataFrame) -> pd.DataFrame:
        """
        Map APO SNP planning data to AWS DemandPlan.

        Args:
            snp_df: DataFrame from APOConnector.extract_snp_plan()

        Returns:
            DataFrame in AWS DemandPlan schema
        """
        logger.info("Mapping APO SNP to AWS DemandPlan")

        demand_plan = pd.DataFrame()

        demand_plan["site_id"] = snp_df["LOCNO"]
        demand_plan["product_id"] = snp_df["MATNR"]
        demand_plan["plan_date"] = pd.to_datetime(snp_df["PLAN_DATE"], errors="coerce")
        demand_plan["forecasted_quantity"] = pd.to_numeric(
            snp_df.get("DEMAND_QTY", 0), errors="coerce"
        )
        demand_plan["unit_of_measure"] = "EA"
        demand_plan["forecast_type"] = "SALES"
        demand_plan["confidence_level"] = 0.85  # Default confidence

        logger.info(f"Mapped {len(demand_plan)} SNP records to DemandPlan")
        return demand_plan

    def map_s4hana_so_to_sales_orders(
        self,
        so_headers: pd.DataFrame,
        so_items: pd.DataFrame,
        vbep_df: pd.DataFrame = None,
        vbuk_df: pd.DataFrame = None,
    ) -> pd.DataFrame:
        """
        Map S/4HANA sales orders (VBAK/VBAP) to AWS SalesOrder.

        Args:
            so_headers: VBAK header data
            so_items: VBAP item data
            vbep_df: Optional VBEP schedule lines for delivery dates
            vbuk_df: Optional VBUK document status for order status

        Returns:
            DataFrame in AWS SalesOrder schema
        """
        logger.info("Mapping S/4HANA SOs to AWS SalesOrder")

        # Merge headers and items
        sos = so_items.merge(
            so_headers[["VBELN", "KUNNR", "ERDAT"]],
            on="VBELN",
            how="left"
        )

        # Join VBEP schedule lines for delivery dates and confirmed qty
        if vbep_df is not None and not vbep_df.empty:
            # Take first schedule line per order/item (lowest ETENR)
            vbep_sorted = vbep_df.sort_values("ETENR")
            vbep_first = vbep_sorted.drop_duplicates(subset=["VBELN", "POSNR"], keep="first")
            sched_cols = ["VBELN", "POSNR"]
            if "EDATU" in vbep_first.columns:
                sched_cols.append("EDATU")
            if "BMENG" in vbep_first.columns:
                sched_cols.append("BMENG")
            sos = sos.merge(vbep_first[sched_cols], on=["VBELN", "POSNR"], how="left")

        # Join VBUK document status
        if vbuk_df is not None and not vbuk_df.empty:
            status_cols = ["VBELN"]
            if "GBSTK" in vbuk_df.columns:
                status_cols.append("GBSTK")  # Overall status
            if len(status_cols) > 1:
                sos = sos.merge(vbuk_df[status_cols].drop_duplicates(subset=["VBELN"]), on="VBELN", how="left")

        sales_orders = pd.DataFrame()

        sales_orders["so_number"] = sos["VBELN"]
        sales_orders["so_line_number"] = sos["POSNR"]
        sales_orders["customer_id"] = sos["KUNNR"]
        sales_orders["product_id"] = sos["MATNR"]
        sales_orders["source_site_id"] = sos["WERKS"]
        sales_orders["order_date"] = pd.to_datetime(sos["ERDAT"], errors="coerce")

        # Delivery date from VBEP.EDATU (schedule line delivery date)
        if "EDATU" in sos.columns:
            sales_orders["requested_delivery_date"] = pd.to_datetime(sos["EDATU"], errors="coerce")
        else:
            sales_orders["requested_delivery_date"] = pd.NaT

        sales_orders["order_quantity"] = pd.to_numeric(sos["KWMENG"], errors="coerce")

        # Confirmed/promised quantity from VBEP.BMENG
        if "BMENG" in sos.columns:
            sales_orders["promised_quantity"] = pd.to_numeric(sos["BMENG"], errors="coerce")
            sales_orders["open_quantity"] = (
                sales_orders["order_quantity"] - sales_orders["promised_quantity"].fillna(0)
            ).clip(lower=0)
        else:
            sales_orders["open_quantity"] = pd.to_numeric(sos["KWMENG"], errors="coerce")

        sales_orders["unit_of_measure"] = _safe_col(sos, "VRKME", "EA")
        sales_orders["unit_price"] = pd.to_numeric(_safe_col(sos, "NETPR", 0), errors="coerce")
        sales_orders["currency"] = _safe_col(sos, "WAERK", "USD")

        # Status from VBUK.GBSTK (overall processing status)
        if "GBSTK" in sos.columns:
            vbuk_status_map = {"A": "OPEN", "B": "PARTIAL", "C": "COMPLETED", "": "OPEN"}
            sales_orders["status"] = sos["GBSTK"].fillna("").map(
                lambda x: vbuk_status_map.get(str(x).strip(), "OPEN")
            )
        else:
            sales_orders["status"] = "OPEN"

        logger.info(f"Mapped {len(sales_orders)} SO lines to SalesOrder")
        return sales_orders

    def map_s4hana_deliveries_to_shipments(
        self,
        delivery_headers: pd.DataFrame,
        delivery_items: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Map S/4HANA deliveries (LIKP/LIPS) to AWS Shipment.

        Args:
            delivery_headers: LIKP header data (includes BOLNR, LIFNR, LDDAT, NTGEW, VOLUM)
            delivery_items: LIPS item data

        Returns:
            DataFrame in AWS Shipment schema
        """
        logger.info("Mapping S/4HANA deliveries to AWS Shipment")

        # Select available header columns for merge
        header_cols = ["VBELN"]
        for col in ["KUNNR", "LFDAT", "WADAT_IST", "BOLNR", "LIFNR", "LDDAT", "NTGEW", "VOLUM", "VOLEH", "VKORG"]:
            if col in delivery_headers.columns:
                header_cols.append(col)

        deliveries = delivery_items.merge(
            delivery_headers[header_cols],
            on="VBELN",
            how="left"
        )

        shipments = pd.DataFrame()

        shipments["shipment_id"] = deliveries["VBELN"]
        shipments["shipment_line_number"] = deliveries["POSNR"]
        shipments["product_id"] = deliveries["MATNR"]
        shipments["source_site_id"] = deliveries["WERKS"]
        shipments["destination_site_id"] = _safe_col(deliveries, "KUNNR", "")
        shipments["shipment_date"] = pd.to_datetime(
            _safe_col(deliveries, "WADAT_IST", _safe_col(deliveries, "LFDAT", None)), errors="coerce"
        )
        shipments["expected_delivery_date"] = pd.to_datetime(
            _safe_col(deliveries, "LFDAT", None), errors="coerce"
        )
        shipments["actual_delivery_date"] = pd.to_datetime(
            _safe_col(deliveries, "LDDAT", _safe_col(deliveries, "WADAT_IST", None)), errors="coerce"
        )
        shipments["shipped_quantity"] = pd.to_numeric(
            _safe_col(deliveries, "LFIMG", 0), errors="coerce"
        )
        shipments["unit_of_measure"] = _safe_col(deliveries, "VRKME", "EA")
        shipments["shipment_type"] = "OUTBOUND"

        # Tracking number from LIKP.BOLNR (bill of lading)
        shipments["tracking_number"] = _safe_col(deliveries, "BOLNR", "").astype(str).str.strip()

        # Carrier from LIKP.LIFNR (forwarding agent)
        shipments["carrier_id"] = _safe_col(deliveries, "LIFNR", "").astype(str).str.strip()

        # Weight/volume from LIKP header
        shipments["weight"] = pd.to_numeric(_safe_col(deliveries, "NTGEW", 0), errors="coerce")
        shipments["volume"] = pd.to_numeric(_safe_col(deliveries, "VOLUM", 0), errors="coerce")
        shipments["volume_unit"] = _safe_col(deliveries, "VOLEH", "").astype(str).str.strip()

        # Order reference from LIPS.VGBEL/VGPOS (sales order that triggered this delivery)
        shipments["order_id"] = _safe_col(deliveries, "VGBEL", "").astype(str).str.strip()
        shipments["order_line_number"] = pd.to_numeric(
            _safe_col(deliveries, "VGPOS", 0), errors="coerce"
        ).fillna(0).astype(int)

        # from_site_id = plant (LIPS.WERKS), already mapped as source_site_id
        # to_site_id = customer site (LIKP.KUNNR → trading partner lookup)
        shipments["from_site_id"] = shipments["source_site_id"]
        shipments["to_site_id"] = shipments["destination_site_id"]

        # Status: if actual delivery date exists → DELIVERED, else SHIPPED
        has_actual = shipments["actual_delivery_date"].notna()
        shipments["status"] = "SHIPPED"
        shipments.loc[has_actual, "status"] = "DELIVERED"

        shipments["source"] = "SAP_LIKP_LIPS"

        logger.info(f"Mapped {len(shipments)} delivery lines to Shipment")
        return shipments

    def validate_schema(self, df: pd.DataFrame, schema: Dict[str, type]) -> bool:
        """
        Validate DataFrame against Supply Chain schema.

        Args:
            df: DataFrame to validate
            schema: Expected schema dictionary

        Returns:
            bool: True if valid
        """
        missing_cols = set(schema.keys()) - set(df.columns)
        if missing_cols:
            logger.warning(f"Missing required columns: {missing_cols}")
            return False

        # Type validation could be added here
        return True

    def export_to_standard_format(
        self,
        df: pd.DataFrame,
        entity_type: str,
        output_path: str
    ):
        """
        Export DataFrame to standard Supply Chain format (CSV/JSON).

        Args:
            df: DataFrame to export
            entity_type: Entity type (Sites, Products, etc.)
            output_path: Output file path
        """
        logger.info(f"Exporting {entity_type} to {output_path}")

        # Convert datetime columns to ISO format
        for col in df.select_dtypes(include=["datetime64"]).columns:
            df[col] = df[col].dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Export based on file extension
        if output_path.endswith(".json"):
            df.to_json(output_path, orient="records", indent=2)
        else:
            df.to_csv(output_path, index=False)

        logger.info(f"Exported {len(df)} {entity_type} records to {output_path}")

    # =========================================================================
    # ATP/CTP Integration Mappings (Phase 3 - SAP ATP Integration)
    # =========================================================================

    # ATP-specific schemas
    PRODUCTION_ORDER_SCHEMA = {
        "order_number": str,
        "order_type": str,
        "product_id": str,
        "site_id": str,
        "planned_quantity": float,
        "confirmed_quantity": float,
        "goods_receipt_quantity": float,
        "start_date": datetime,
        "finish_date": datetime,
        "status": str,
    }

    ATP_CHECK_SCHEMA = {
        "product_id": str,
        "site_id": str,
        "check_date": datetime,
        "available_qty": float,
        "scheduled_receipts_qty": float,
        "reserved_qty": float,
        "safety_stock_qty": float,
        "atp_qty": float,
        "source": str,
    }

    INV_POLICY_SCHEMA = {
        "product_id": str,
        "site_id": str,
        "ss_policy": str,  # abs_level, doc_dem, doc_fcst, sl
        "ss_quantity": float,
        "ss_days": int,
        "review_period": int,
        "lead_time_days": int,
        "source": str,
    }

    def map_s4hana_production_orders(
        self,
        afko_headers: pd.DataFrame,
        afpo_items: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Map S/4HANA production orders (AFKO/AFPO) to ProductionOrder schema.

        Production orders are used for:
        - CTP: Committed capacity reduces available-to-promise
        - ATP: Scheduled receipts from production increase supply

        Args:
            afko_headers: DataFrame from AFKO (production order headers)
            afpo_items: DataFrame from AFPO (production order items)

        Returns:
            DataFrame in ProductionOrder schema
        """
        logger.info("Mapping S/4HANA production orders to ProductionOrder schema")

        if afko_headers.empty:
            return pd.DataFrame(columns=list(self.PRODUCTION_ORDER_SCHEMA.keys()))

        # Merge headers and items
        orders = afpo_items.merge(
            afko_headers[['AUFNR', 'AUART', 'STAT', 'GSTRP', 'GLTRP']],
            on='AUFNR',
            how='left'
        ) if not afpo_items.empty else afko_headers.copy()

        prod_orders = pd.DataFrame()

        prod_orders['order_number'] = orders['AUFNR'].astype(str).str.strip()
        prod_orders['order_type'] = orders.get('AUART', 'PP01').astype(str).str.strip()
        prod_orders['product_id'] = orders['MATNR'].astype(str).str.strip()
        prod_orders['site_id'] = orders['WERKS'].astype(str).str.strip()
        prod_orders['planned_quantity'] = pd.to_numeric(
            orders.get('PSMNG', orders.get('GAMNG', 0)), errors='coerce'
        ).fillna(0)
        prod_orders['confirmed_quantity'] = prod_orders['planned_quantity']  # Simplified
        prod_orders['goods_receipt_quantity'] = pd.to_numeric(
            orders.get('WEMNG', 0), errors='coerce'
        ).fillna(0)
        prod_orders['start_date'] = pd.to_datetime(
            orders.get('GSTRP', orders.get('FTRMI')), format='%Y%m%d', errors='coerce'
        )
        prod_orders['finish_date'] = pd.to_datetime(
            orders.get('GLTRP', orders.get('FTRMS')), format='%Y%m%d', errors='coerce'
        )

        # Map SAP status to standard status
        status_map = {
            'REL': 'RELEASED',
            'CNF': 'CONFIRMED',
            'CRTD': 'PLANNED',
            'TECO': 'COMPLETED',
            'DLFL': 'DELETED',
        }
        prod_orders['status'] = orders.get('STAT', 'REL').apply(
            lambda x: status_map.get(str(x).strip()[:4], 'RELEASED') if pd.notna(x) else 'RELEASED'
        )

        # Calculate open quantity (planned - received)
        prod_orders['open_quantity'] = prod_orders['planned_quantity'] - prod_orders['goods_receipt_quantity']

        logger.info(f"Mapped {len(prod_orders)} production orders")
        return prod_orders

    def map_s4hana_schedule_lines_to_supply_plan(
        self,
        eket_df: pd.DataFrame,
        ekpo_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Map PO schedule lines (EKET) to SupplyPlan schema.

        Schedule lines represent confirmed delivery dates and quantities for
        purchase orders. They are a key input to ATP (scheduled receipts).

        Args:
            eket_df: DataFrame from EKET (PO schedule lines)
            ekpo_df: DataFrame from EKPO (PO items) for material/plant info

        Returns:
            DataFrame in SupplyPlan schema
        """
        logger.info("Mapping S/4HANA schedule lines to SupplyPlan schema")

        if eket_df.empty:
            return pd.DataFrame(columns=list(self.SUPPLY_PLAN_SCHEMA.keys()))

        # Merge schedule lines with PO items to get material and plant
        merged = eket_df.merge(
            ekpo_df[['EBELN', 'EBELP', 'MATNR', 'WERKS']],
            on=['EBELN', 'EBELP'],
            how='left'
        ) if not ekpo_df.empty else eket_df

        supply_plan = pd.DataFrame()

        supply_plan['site_id'] = merged.get('WERKS', '').astype(str).str.strip()
        supply_plan['product_id'] = merged.get('MATNR', '').astype(str).str.strip()
        supply_plan['plan_date'] = pd.to_datetime(
            merged['EINDT'], format='%Y%m%d', errors='coerce'
        )

        # Calculate open quantity (scheduled - received)
        menge = pd.to_numeric(merged.get('MENGE', 0), errors='coerce').fillna(0)
        wemng = pd.to_numeric(merged.get('WEMNG', 0), errors='coerce').fillna(0)
        supply_plan['planned_quantity'] = menge - wemng

        supply_plan['unit_of_measure'] = 'EA'
        supply_plan['source_type'] = 'PURCHASE'  # Schedule lines are from POs
        supply_plan['source_site_id'] = ''  # Vendor - would need EKKO join
        supply_plan['lead_time_days'] = 0  # Would calculate from order date

        # Add PO reference
        supply_plan['po_number'] = merged['EBELN'].astype(str).str.strip()
        supply_plan['po_line_number'] = merged['EBELP'].astype(str).str.strip()
        supply_plan['schedule_line'] = merged.get('ETENR', '0001').astype(str).str.strip()

        # Filter to only open schedule lines
        supply_plan = supply_plan[supply_plan['planned_quantity'] > 0]

        logger.info(f"Mapped {len(supply_plan)} schedule lines to SupplyPlan")
        return supply_plan

    def map_marc_to_inv_policy(
        self,
        marc_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Map MARC data to InvPolicy schema (safety stock, lead times).

        MARC contains plant-specific material settings including:
        - EISBE: Safety stock quantity
        - PLIFZ: Planned delivery time (days)
        - DZEIT: In-house production time (days)
        - MTVFP: Availability check group

        Args:
            marc_df: DataFrame from MARC with ATP fields

        Returns:
            DataFrame in InvPolicy schema
        """
        logger.info("Mapping S/4HANA MARC to InvPolicy schema")

        if marc_df.empty:
            return pd.DataFrame(columns=list(self.INV_POLICY_SCHEMA.keys()))

        inv_policy = pd.DataFrame()

        inv_policy['site_id'] = marc_df['WERKS'].astype(str).str.strip()
        inv_policy['product_id'] = marc_df['MATNR'].astype(str).str.strip()

        # Safety stock: EISBE is absolute quantity, SHZET is safety time in days
        eisbe = pd.to_numeric(_safe_col(marc_df, 'EISBE', 0), errors='coerce').fillna(0)
        shzet = pd.to_numeric(_safe_col(marc_df, 'SHZET', 0), errors='coerce').fillna(0)

        # Determine ss_policy from MRP type and available parameters
        # VB=reorder point, VV=forecast-based, V1/V2=MRP auto
        dismm = _safe_col(marc_df, 'DISMM', '').astype(str).str.strip()
        inv_policy['ss_policy'] = 'abs_level'
        inv_policy.loc[shzet > 0, 'ss_policy'] = 'doc_dem'  # Safety time = days-of-coverage
        inv_policy['ss_quantity'] = eisbe
        inv_policy['ss_days'] = shzet.astype(int)

        # Lead time from PLIFZ (planned delivery time) or DZEIT (production time)
        plifz = pd.to_numeric(_safe_col(marc_df, 'PLIFZ', 0), errors='coerce').fillna(0)
        dzeit = pd.to_numeric(_safe_col(marc_df, 'DZEIT', 0), errors='coerce').fillna(0)
        inv_policy['lead_time_days'] = plifz.where(plifz > 0, dzeit).astype(int)

        # Review period from forecast horizon or default to lead time
        fhori = pd.to_numeric(_safe_col(marc_df, 'FHORI', 0), errors='coerce').fillna(0)
        inv_policy['review_period'] = fhori.where(fhori > 0, inv_policy['lead_time_days']).astype(int)

        # Reorder point from MINBE
        inv_policy['reorder_point'] = pd.to_numeric(
            _safe_col(marc_df, 'MINBE', 0), errors='coerce'
        ).fillna(0)

        # Min/max order quantity, rounding value, max stock level
        inv_policy['min_order_quantity'] = pd.to_numeric(
            _safe_col(marc_df, 'BSTMI', 0), errors='coerce'
        ).fillna(0)
        inv_policy['max_order_quantity'] = pd.to_numeric(
            _safe_col(marc_df, 'BSTMA', 0), errors='coerce'
        ).fillna(0)
        inv_policy['fixed_order_quantity'] = pd.to_numeric(
            _safe_col(marc_df, 'BSTRF', 0), errors='coerce'
        ).fillna(0)
        inv_policy['order_up_to_level'] = pd.to_numeric(
            _safe_col(marc_df, 'MABST', 0), errors='coerce'
        ).fillna(0)

        # Service level indicator
        inv_policy['service_level_indicator'] = _safe_col(marc_df, 'SBDKZ', '').astype(str).str.strip()

        # MRP settings for reference
        inv_policy['mrp_controller'] = _safe_col(marc_df, 'DISPO', '').astype(str).str.strip()
        inv_policy['mrp_type'] = dismm
        inv_policy['availability_check_group'] = _safe_col(marc_df, 'MTVFP', '').astype(str).str.strip()

        inv_policy['source'] = 'SAP_MARC'

        logger.info(f"Mapped {len(inv_policy)} MARC records to InvPolicy")
        return inv_policy

    def map_reservations_to_allocations(
        self,
        resb_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Map material reservations (RESB) to allocation records.

        Reservations represent committed/allocated inventory that reduces ATP.

        Args:
            resb_df: DataFrame from RESB (material reservations)

        Returns:
            DataFrame with allocation data
        """
        logger.info("Mapping S/4HANA reservations to allocations")

        if resb_df.empty:
            return pd.DataFrame()

        allocations = pd.DataFrame()

        allocations['reservation_number'] = resb_df['RSNUM'].astype(str).str.strip()
        allocations['reservation_item'] = resb_df['RSPOS'].astype(str).str.strip()
        allocations['product_id'] = resb_df['MATNR'].astype(str).str.strip()
        allocations['site_id'] = resb_df['WERKS'].astype(str).str.strip()
        allocations['storage_location'] = resb_df.get('LGORT', '').astype(str).str.strip()

        # Calculate open reservation quantity
        bdmng = pd.to_numeric(resb_df.get('BDMNG', 0), errors='coerce').fillna(0)
        enmng = pd.to_numeric(resb_df.get('ENMNG', 0), errors='coerce').fillna(0)
        allocations['allocated_quantity'] = bdmng - enmng

        allocations['requirement_date'] = pd.to_datetime(
            resb_df.get('BDTER'), format='%Y%m%d', errors='coerce'
        )
        allocations['production_order'] = resb_df.get('AUFNR', '').astype(str).str.strip()
        allocations['is_final_issue'] = resb_df.get('KZEAR', '') == 'X'

        # Filter to only open reservations
        allocations = allocations[allocations['allocated_quantity'] > 0]

        logger.info(f"Mapped {len(allocations)} reservations to allocations")
        return allocations

    def calculate_atp_from_components(
        self,
        inventory_df: pd.DataFrame,
        scheduled_receipts_df: pd.DataFrame,
        allocations_df: pd.DataFrame,
        safety_stock_df: pd.DataFrame,
        product_id: str,
        site_id: str
    ) -> Dict:
        """
        Calculate ATP from component data frames.

        ATP = On-Hand + Scheduled Receipts - Allocations - Safety Stock

        Args:
            inventory_df: Current inventory levels
            scheduled_receipts_df: Scheduled supply (POs, production orders)
            allocations_df: Committed/reserved quantities
            safety_stock_df: Safety stock policies
            product_id: Product to calculate ATP for
            site_id: Site to calculate ATP for

        Returns:
            Dict with ATP calculation breakdown
        """
        # Filter to specific product/site
        inv = inventory_df[
            (inventory_df['product_id'] == product_id) &
            (inventory_df['site_id'] == site_id)
        ]
        receipts = scheduled_receipts_df[
            (scheduled_receipts_df['product_id'] == product_id) &
            (scheduled_receipts_df['site_id'] == site_id)
        ]
        allocs = allocations_df[
            (allocations_df['product_id'] == product_id) &
            (allocations_df['site_id'] == site_id)
        ]
        ss = safety_stock_df[
            (safety_stock_df['product_id'] == product_id) &
            (safety_stock_df['site_id'] == site_id)
        ]

        on_hand = float(inv['available_quantity'].sum()) if not inv.empty else 0
        scheduled = float(receipts['planned_quantity'].sum()) if not receipts.empty else 0
        allocated = float(allocs['allocated_quantity'].sum()) if not allocs.empty else 0
        safety_stock = float(ss['ss_quantity'].iloc[0]) if not ss.empty else 0

        atp = max(0, on_hand + scheduled - allocated - safety_stock)

        return {
            'product_id': product_id,
            'site_id': site_id,
            'on_hand': on_hand,
            'scheduled_receipts': scheduled,
            'allocated': allocated,
            'safety_stock': safety_stock,
            'atp': atp,
            'timestamp': datetime.now().isoformat()
        }

    # ==========================================================================
    # Config Builder Mapping Methods
    # ==========================================================================

    def map_vendor_products(
        self,
        eina_df: pd.DataFrame,
        eine_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Map purchasing info records (EINA/EINE) to vendor_product.

        Returns vendor-product relationships with pricing and MOQs.
        """
        logger.info("Mapping purchasing info records to vendor_product")

        if eina_df.empty:
            return pd.DataFrame()

        merged = eina_df.merge(eine_df, on="INFNR", how="left", suffixes=("", "_eine")) if not eine_df.empty else eina_df.copy()
        # Resolve column collisions — prefer EINA (left side, no suffix)
        for col in ["MATNR", "LIFNR"]:
            if col not in merged.columns and f"{col}_eine" in merged.columns:
                merged[col] = merged[f"{col}_eine"]

        def _col(name: str, default=""):
            """Find column, checking _eine suffix from merge."""
            if name in merged.columns:
                return merged[name]
            alt = f"{name}_eine"
            if alt in merged.columns:
                return merged[alt]
            return pd.Series(default, index=merged.index)

        result = pd.DataFrame()
        result["vendor_id"] = merged["LIFNR"].astype(str).str.strip()
        result["product_id"] = merged["MATNR"].astype(str).str.strip()
        result["info_record"] = merged["INFNR"].astype(str).str.strip()
        result["net_price"] = pd.to_numeric(_col("NETPR", 0), errors="coerce").fillna(0)
        result["currency"] = _col("WAERS", "USD").astype(str).str.strip()
        result["price_unit"] = pd.to_numeric(_col("PEINH", 1), errors="coerce").fillna(1)
        result["min_order_qty"] = pd.to_numeric(_col("MINBM", 0), errors="coerce").fillna(0)
        result["standard_order_qty"] = pd.to_numeric(_col("NORBM", 0), errors="coerce").fillna(0)
        result["planned_delivery_time"] = pd.to_numeric(_col("APLFZ", 0), errors="coerce").fillna(0)

        # Remove records flagged for deletion
        if "LOEKZ" in merged.columns:
            result = result[merged["LOEKZ"].isna() | (merged["LOEKZ"] == "")]

        logger.info(f"Mapped {len(result)} vendor-product records")
        return result

    def map_vendor_lead_times(
        self,
        eina_df: pd.DataFrame,
        eine_df: pd.DataFrame,
        eord_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Map EINA/EINE + EORD to vendor_lead_time per vendor-product-site.

        Priority: EINE.APLFZ (planned delivery time) > MARC.PLIFZ (fallback).
        """
        logger.info("Mapping vendor lead times")

        if eina_df.empty:
            return pd.DataFrame()

        # Merge info records (suffixes handle column collisions between EINA and EINE)
        merged = eina_df.merge(eine_df, on="INFNR", how="left", suffixes=("", "_eine")) if not eine_df.empty else eina_df.copy()

        # Resolve MATNR/LIFNR — prefer EINA (left side, no suffix)
        for col in ["MATNR", "LIFNR"]:
            if col not in merged.columns and f"{col}_eine" in merged.columns:
                merged[col] = merged[f"{col}_eine"]

        # Get plant assignments from EORD
        if not eord_df.empty and "WERKS" in eord_df.columns:
            # Each EORD row links (MATNR, WERKS, LIFNR) — join on vendor+material
            eord_cols = [c for c in ["MATNR", "WERKS", "LIFNR"] if c in eord_df.columns]
            plant_map = eord_df[eord_cols].drop_duplicates()
            # Drop any existing WERKS from merged before joining to avoid _x/_y
            if "WERKS" in merged.columns:
                merged = merged.drop(columns=["WERKS"])
            join_cols = [c for c in ["MATNR", "LIFNR"] if c in plant_map.columns and c in merged.columns]
            if join_cols:
                merged = merged.merge(plant_map, on=join_cols, how="left")

        if "WERKS" not in merged.columns:
            merged["WERKS"] = ""

        result = pd.DataFrame()
        result["vendor_id"] = merged["LIFNR"].astype(str).str.strip()
        result["product_id"] = merged["MATNR"].astype(str).str.strip()
        result["site_id"] = merged["WERKS"].astype(str).str.strip()
        # Resolve APLFZ which may have been suffixed from EINE merge
        aplfz_col = "APLFZ" if "APLFZ" in merged.columns else ("APLFZ_eine" if "APLFZ_eine" in merged.columns else None)
        result["lead_time_days"] = pd.to_numeric(merged[aplfz_col], errors="coerce").fillna(0).astype(int) if aplfz_col else 0
        ekorg_col = "EKORG" if "EKORG" in merged.columns else ("EKORG_eine" if "EKORG_eine" in merged.columns else None)
        result["purchasing_org"] = merged[ekorg_col].astype(str).str.strip() if ekorg_col else ""

        result = result[result["lead_time_days"] > 0].drop_duplicates()

        logger.info(f"Mapped {len(result)} vendor lead time records")
        return result

    def map_sourcing_rules(self, eord_df: pd.DataFrame) -> pd.DataFrame:
        """
        Map source list (EORD) to sourcing_rules.

        EORD defines approved vendor-plant assignments with priority.
        """
        logger.info("Mapping EORD source list to sourcing_rules")

        if eord_df.empty:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["product_id"] = eord_df["MATNR"].astype(str).str.strip()
        result["site_id"] = eord_df["WERKS"].astype(str).str.strip()
        result["source_id"] = eord_df["LIFNR"].astype(str).str.strip()

        # Map procurement type
        beskz = _safe_col(eord_df, "BESKZ", "F").astype(str).str.strip()
        source_type_map = {"F": "buy", "E": "manufacture", "U": "subcontract"}
        result["source_type"] = beskz.map(source_type_map).fillna("buy")

        # NOTKZ: 1=normal (usable), 2=blocked
        notkz = _safe_col(eord_df, "NOTKZ", "1").astype(str).str.strip()
        result["is_active"] = notkz != "2"

        result["fixed_vendor"] = _safe_col(eord_df, "FLIFN", "").astype(str).str.strip() == "X"
        result["valid_from"] = pd.to_datetime(_safe_col(eord_df, "VDATU", None), format="%Y%m%d", errors="coerce")
        result["valid_to"] = pd.to_datetime(_safe_col(eord_df, "BDATU", None), format="%Y%m%d", errors="coerce")

        # Priority from sequence number (lower = higher priority)
        result["priority"] = pd.to_numeric(_safe_col(eord_df, "ZEESSION", 1), errors="coerce").fillna(1).astype(int)

        result = result[result["is_active"]].drop(columns=["is_active"])

        logger.info(f"Mapped {len(result)} sourcing rules")
        return result

    def map_company(
        self, t001_df: pd.DataFrame, adrc_df: pd.DataFrame = None,
        t001w_df: pd.DataFrame = None,
    ) -> pd.DataFrame:
        """Map company codes (T001) to company entities.

        Enriches with ADRC address data via T001W.ADRNR join when available.
        T001.FABKL provides the factory calendar ID.
        """
        logger.info("Mapping T001 to company")

        if t001_df.empty:
            return pd.DataFrame()

        src = t001_df.copy()

        # Join ADRC via T001W.ADRNR for the first plant of each company
        if adrc_df is not None and not adrc_df.empty and t001w_df is not None and not t001w_df.empty:
            plant_addr = t001w_df[["BUKRS", "ADRNR"]].dropna(subset=["ADRNR"]).drop_duplicates(subset=["BUKRS"], keep="first")
            plant_addr["ADRNR"] = plant_addr["ADRNR"].astype(str).str.strip()
            adrc_cols = ["ADDRNUMBER"]
            for c in ["STREET", "CITY1", "REGION", "POST_CODE1", "COUNTRY", "TEL_NUMBER", "TIME_ZONE"]:
                if c in adrc_df.columns:
                    adrc_cols.append(c)
            adrc_dedup = adrc_df[adrc_cols].drop_duplicates(subset=["ADDRNUMBER"])
            plant_addr = plant_addr.merge(adrc_dedup, left_on="ADRNR", right_on="ADDRNUMBER", how="left")
            src = src.merge(plant_addr.drop(columns=["ADRNR", "ADDRNUMBER"], errors="ignore"), on="BUKRS", how="left")

        result = pd.DataFrame()
        result["company_id"] = src["BUKRS"].astype(str).str.strip()
        result["company_name"] = _safe_col(src, "BUTXT", "").astype(str).str.strip()
        result["country"] = _safe_col(src, "LAND1", "").astype(str).str.strip()
        result["currency"] = _safe_col(src, "WAERS", "").astype(str).str.strip()
        result["address_1"] = _safe_col(src, "STREET", "").astype(str).str.strip()
        result["city"] = _safe_col(src, "CITY1", "").astype(str).str.strip()
        result["state_prov"] = _safe_col(src, "REGION", "").astype(str).str.strip()
        result["postal_code"] = _safe_col(src, "POST_CODE1", "").astype(str).str.strip()
        result["phone_number"] = _safe_col(src, "TEL_NUMBER", "").astype(str).str.strip()
        result["time_zone"] = _safe_col(src, "TIME_ZONE", "").astype(str).str.strip()
        result["calendar_id"] = _safe_col(src, "FABKL", "").astype(str).str.strip() if "FABKL" in src.columns else ""

        logger.info(f"Mapped {len(result)} companies")
        return result

    def map_geography(self, adrc_df: pd.DataFrame) -> pd.DataFrame:
        """Map addresses (ADRC) to geography entities.

        Enriches with latitude/longitude, time_zone, and phone_number from ADRC
        when those columns are populated (rare in IDES, common in production).
        """
        logger.info("Mapping ADRC to geography")

        if adrc_df.empty:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["address_id"] = adrc_df["ADDRNUMBER"].astype(str).str.strip()
        result["name"] = _safe_col(adrc_df, "NAME1", "").astype(str).str.strip()
        result["street"] = _safe_col(adrc_df, "STREET", "").astype(str).str.strip()
        result["city"] = _safe_col(adrc_df, "CITY1", "").astype(str).str.strip()
        result["region"] = _safe_col(adrc_df, "REGION", "").astype(str).str.strip()
        result["country"] = _safe_col(adrc_df, "COUNTRY", "").astype(str).str.strip()
        result["postal_code"] = _safe_col(adrc_df, "POST_CODE1", "").astype(str).str.strip()
        result["phone_number"] = _safe_col(adrc_df, "TEL_NUMBER", "").astype(str).str.strip()
        result["time_zone"] = _safe_col(adrc_df, "TIME_ZONE", "").astype(str).str.strip()
        # Lat/lon from ADRC — rarely populated in IDES but available in production SAP systems
        result["latitude"] = pd.to_numeric(_safe_col(adrc_df, "LATITUDE", np.nan), errors="coerce")
        result["longitude"] = pd.to_numeric(_safe_col(adrc_df, "LONGITUDE", np.nan), errors="coerce")

        logger.info(f"Mapped {len(result)} geography records")
        return result

    def map_production_process(
        self,
        plko_df: pd.DataFrame,
        plpo_df: pd.DataFrame,
        marc_df: pd.DataFrame = None,
    ) -> pd.DataFrame:
        """
        Map routings (PLKO/PLPO) to production_process.

        Combines header validity/plant info with operation-level times.
        Optionally enriches with MARC.AUSSS (assembly scrap %) for yield_percentage.
        """
        logger.info("Mapping routings to production_process")

        if plpo_df.empty:
            return pd.DataFrame()

        # Merge header info
        if not plko_df.empty:
            merged = plpo_df.merge(
                plko_df[["PLNTY", "PLNNR", "PLNAL", "WERKS"]].drop_duplicates(),
                on=["PLNTY", "PLNNR"],
                how="left",
            )
        else:
            merged = plpo_df

        result = pd.DataFrame()
        result["process_id"] = merged["PLNNR"].astype(str).str.strip()
        result["operation_number"] = _safe_col(merged, "VORNR", _safe_col(merged, "PLNKN", "")).astype(str).str.strip()
        result["site_id"] = _safe_col(merged, "WERKS", "").astype(str).str.strip()
        result["work_center_id"] = _safe_col(merged, "ARBPL", _safe_col(merged, "ARBID", "")).astype(str).str.strip()
        result["setup_time"] = pd.to_numeric(_safe_col(merged, "VGW01", 0), errors="coerce").fillna(0)
        result["machine_time"] = pd.to_numeric(_safe_col(merged, "VGW02", 0), errors="coerce").fillna(0)
        result["labor_time"] = pd.to_numeric(_safe_col(merged, "VGW03", 0), errors="coerce").fillna(0)
        result["base_quantity"] = pd.to_numeric(_safe_col(merged, "BMSCH", 1), errors="coerce").fillna(1)

        # Yield from MARC.AUSSS (assembly scrap %) — yield = 100 - scrap%
        if marc_df is not None and not marc_df.empty and "AUSSS" in marc_df.columns:
            marc_yield = marc_df[["MATNR", "WERKS", "AUSSS"]].copy()
            marc_yield["MATNR"] = marc_yield["MATNR"].astype(str).str.strip()
            marc_yield["WERKS"] = marc_yield["WERKS"].astype(str).str.strip()
            marc_yield["_yield"] = 100.0 - pd.to_numeric(marc_yield["AUSSS"], errors="coerce").fillna(0)
            # Attach yield via PLKO material assignment (process_id links to material routing)
            # For now, join on site_id since routings are plant-specific
            if "MATNR" in merged.columns:
                yield_map = marc_yield.drop_duplicates(subset=["MATNR", "WERKS"])
                merged_matnr = _safe_col(merged, "MATNR", "").astype(str).str.strip()
                merged_werks = result["site_id"]
                # Create a composite key for lookup
                yield_map["_key"] = yield_map["MATNR"] + "|" + yield_map["WERKS"]
                yield_dict = yield_map.set_index("_key")["_yield"].to_dict()
                result["yield_percentage"] = (merged_matnr + "|" + merged_werks).map(yield_dict)
            else:
                result["yield_percentage"] = np.nan
        else:
            result["yield_percentage"] = np.nan

        result["source"] = "SAP_PLKO_PLPO"

        logger.info(f"Mapped {len(result)} production process operations")
        return result

    def map_transportation_lanes_from_apo(
        self,
        trlane_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Map APO transportation lanes (/SAPAPO/TRLANE) to transportation_lane.

        This is the highest-quality source for network edges.
        """
        logger.info("Mapping APO transportation lanes")

        if trlane_df.empty:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["source_site_id"] = trlane_df["LOCFR"].astype(str).str.strip()
        result["destination_site_id"] = trlane_df["LOCTO"].astype(str).str.strip()
        result["product_id"] = _safe_col(trlane_df, "MATID", "").astype(str).str.strip()
        result["lead_time_days"] = pd.to_numeric(_safe_col(trlane_df, "TRANSTIME", 0), errors="coerce").fillna(0).astype(int)
        result["capacity"] = pd.to_numeric(_safe_col(trlane_df, "CAPACITY", 0), errors="coerce").fillna(0)
        result["transport_mode"] = _safe_col(trlane_df, "TRANSMODE", "").astype(str).str.strip()
        result["cost_per_unit"] = pd.to_numeric(_safe_col(trlane_df, "TRANSCOST", 0), errors="coerce").fillna(0)

        logger.info(f"Mapped {len(result)} transportation lanes from APO")
        return result

    def map_market_from_customers(
        self,
        knvv_df: pd.DataFrame,
        kna1_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Map customer sales data (KNVV) + customer master (KNA1) to market entities.

        Groups customers by sales district / customer group for demand segmentation.
        """
        logger.info("Mapping KNVV/KNA1 to market entities")

        if knvv_df.empty:
            return pd.DataFrame()

        # Merge customer name from KNA1
        if not kna1_df.empty and "KUNNR" in kna1_df.columns:
            merged = knvv_df.merge(
                kna1_df[["KUNNR", "NAME1"]].drop_duplicates(),
                on="KUNNR",
                how="left",
            )
        else:
            merged = knvv_df.copy()
            merged["NAME1"] = ""

        result = pd.DataFrame()
        result["customer_id"] = merged["KUNNR"].astype(str).str.strip()
        result["customer_name"] = _safe_col(merged, "NAME1", "").astype(str).str.strip()
        result["sales_org"] = _safe_col(merged, "VKORG", "").astype(str).str.strip()
        result["distribution_channel"] = _safe_col(merged, "VTWEG", "").astype(str).str.strip()
        result["division"] = _safe_col(merged, "SPART", "").astype(str).str.strip()
        result["customer_group"] = _safe_col(merged, "KDGRP", "").astype(str).str.strip()
        result["sales_district"] = _safe_col(merged, "BZIRK", "").astype(str).str.strip()

        logger.info(f"Mapped {len(result)} market records from customer data")
        return result

    def map_bom_headers(self, stko_df: pd.DataFrame) -> pd.DataFrame:
        """Map BOM headers (STKO) for enriching STPO items with header context."""
        logger.info("Mapping STKO BOM headers")

        if stko_df.empty:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["bom_number"] = stko_df["STLNR"].astype(str).str.strip()
        result["alternative"] = _safe_col(stko_df, "STLAL", "1").astype(str).str.strip()
        result["base_quantity"] = pd.to_numeric(_safe_col(stko_df, "BMENG", 1), errors="coerce").fillna(1)
        result["base_uom"] = _safe_col(stko_df, "BMEIN", "EA").astype(str).str.strip()
        result["bom_status"] = _safe_col(stko_df, "STLST", "").astype(str).str.strip()

        logger.info(f"Mapped {len(result)} BOM headers")
        return result

    def map_material_uom(self, marm_df: pd.DataFrame) -> pd.DataFrame:
        """Map material UOM conversions (MARM) for unit conversion enrichment."""
        logger.info("Mapping MARM UOM conversions")

        if marm_df.empty:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["product_id"] = marm_df["MATNR"].astype(str).str.strip()
        result["alt_uom"] = marm_df["MEINH"].astype(str).str.strip()
        result["numerator"] = pd.to_numeric(marm_df.get("UMREZ", 1), errors="coerce").fillna(1)
        result["denominator"] = pd.to_numeric(marm_df.get("UMREN", 1), errors="coerce").fillna(1)
        result["conversion_factor"] = result["numerator"] / result["denominator"]

        logger.info(f"Mapped {len(result)} UOM conversion records")
        return result

    # ==========================================================================
    # Phase 2 Staging Mappings — Complete Entity Coverage
    # ==========================================================================

    def map_trading_partners(
        self, lfa1_df: pd.DataFrame, kna1_df: pd.DataFrame,
        adrc_df: pd.DataFrame = None,
    ) -> pd.DataFrame:
        """Map SAP vendor master (LFA1) and customer master (KNA1) to TradingPartner.

        Enriches with:
        - ADRC lat/lon and time_zone via ADRNR join
        - ERDAT → eff_start_date (creation date)
        - STCD3 → duns_number (tax number 3 sometimes stores DUNS)
        """
        logger.info("Mapping LFA1/KNA1 to TradingPartner")

        def _enrich_with_adrc(df: pd.DataFrame, result: pd.DataFrame) -> pd.DataFrame:
            """Enrich result with lat/lon/timezone from ADRC via ADRNR."""
            if adrc_df is None or adrc_df.empty or "ADRNR" not in df.columns:
                result["latitude"] = np.nan
                result["longitude"] = np.nan
                result["time_zone"] = ""
                return result
            adrnr = _safe_col(df, "ADRNR", "").astype(str).str.strip()
            adrc_cols = ["ADDRNUMBER"]
            for c in ["TIME_ZONE", "LATITUDE", "LONGITUDE"]:
                if c in adrc_df.columns:
                    adrc_cols.append(c)
            adrc_lookup = adrc_df[adrc_cols].drop_duplicates(subset=["ADDRNUMBER"])
            adrc_lookup["ADDRNUMBER"] = adrc_lookup["ADDRNUMBER"].astype(str).str.strip()
            addr_map = adrc_lookup.set_index("ADDRNUMBER")
            result["time_zone"] = adrnr.map(addr_map["TIME_ZONE"]).fillna("") if "TIME_ZONE" in addr_map.columns else ""
            result["latitude"] = adrnr.map(addr_map["LATITUDE"]).astype(float) if "LATITUDE" in addr_map.columns else np.nan
            result["longitude"] = adrnr.map(addr_map["LONGITUDE"]).astype(float) if "LONGITUDE" in addr_map.columns else np.nan
            return result

        frames = []
        if not lfa1_df.empty:
            v = pd.DataFrame()
            v["id"] = lfa1_df["LIFNR"].astype(str).str.strip()
            v["tpartner_type"] = "vendor"
            v["description"] = _safe_col(lfa1_df, "NAME1", "").astype(str).str.strip()
            v["address_1"] = _safe_col(lfa1_df, "STRAS", "").astype(str).str.strip()
            v["city"] = _safe_col(lfa1_df, "ORT01", "").astype(str).str.strip()
            v["state_prov"] = _safe_col(lfa1_df, "REGIO", "").astype(str).str.strip()
            v["postal_code"] = _safe_col(lfa1_df, "PSTLZ", "").astype(str).str.strip()
            v["country"] = _safe_col(lfa1_df, "LAND1", "").astype(str).str.strip()
            v["phone_number"] = _safe_col(lfa1_df, "TELF1", "").astype(str).str.strip()
            v["is_active"] = (_safe_col(lfa1_df, "SPERM", "").astype(str).str.strip() != "X").map({True: "true", False: "false"})
            v["eff_start_date"] = pd.to_datetime(_safe_col(lfa1_df, "ERDAT", None), errors="coerce")
            v["duns_number"] = _safe_col(lfa1_df, "STCD3", "").astype(str).str.strip() if "STCD3" in lfa1_df.columns else ""
            v = _enrich_with_adrc(lfa1_df, v)
            v["source"] = "SAP_LFA1"
            frames.append(v)
        if not kna1_df.empty:
            c = pd.DataFrame()
            c["id"] = kna1_df["KUNNR"].astype(str).str.strip()
            c["tpartner_type"] = "customer"
            c["description"] = _safe_col(kna1_df, "NAME1", "").astype(str).str.strip()
            c["address_1"] = _safe_col(kna1_df, "STRAS", "").astype(str).str.strip()
            c["city"] = _safe_col(kna1_df, "ORT01", "").astype(str).str.strip()
            c["state_prov"] = _safe_col(kna1_df, "REGIO", "").astype(str).str.strip()
            c["postal_code"] = _safe_col(kna1_df, "PSTLZ", "").astype(str).str.strip()
            c["country"] = _safe_col(kna1_df, "LAND1", "").astype(str).str.strip()
            c["phone_number"] = _safe_col(kna1_df, "TELF1", "").astype(str).str.strip()
            c["is_active"] = (_safe_col(kna1_df, "AUFSD", "").astype(str).str.strip() != "X").map({True: "true", False: "false"})
            c["eff_start_date"] = pd.to_datetime(_safe_col(kna1_df, "ERDAT", None), errors="coerce")
            c["duns_number"] = _safe_col(kna1_df, "STCD3", "").astype(str).str.strip() if "STCD3" in kna1_df.columns else ""
            c = _enrich_with_adrc(kna1_df, c)
            c["source"] = "SAP_KNA1"
            frames.append(c)
        if not frames:
            return pd.DataFrame()
        result = pd.concat(frames, ignore_index=True)
        logger.info(f"Mapped {len(result)} trading partner records")
        return result

    def map_bom_items(
        self, stpo_df: pd.DataFrame, stko_df: pd.DataFrame, marc_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """Map BOM items (STPO) to ProductBom. Resolves parent via MARC.STLNR."""
        logger.info("Mapping STPO/STKO to ProductBom")
        if stpo_df.empty:
            return pd.DataFrame()
        items = stpo_df.copy()
        if not stko_df.empty and "STLNR" in stko_df.columns:
            hcols = [c for c in ["STLNR", "BMENG", "STLAL"] if c in stko_df.columns]
            items = items.merge(stko_df[hcols].drop_duplicates(subset=["STLNR"]), on="STLNR", how="left")
        if not marc_df.empty and "STLNR" in marc_df.columns:
            pm = marc_df[["MATNR", "WERKS", "STLNR"]].dropna(subset=["STLNR"]).drop_duplicates(subset=["STLNR"])
            pm = pm.rename(columns={"MATNR": "PARENT_MATNR", "WERKS": "PARENT_WERKS"})
            items = items.merge(pm, on="STLNR", how="left")
        else:
            items["PARENT_MATNR"] = ""
            items["PARENT_WERKS"] = ""
        result = pd.DataFrame()
        result["product_id"] = items["PARENT_MATNR"].astype(str).str.strip()
        result["component_product_id"] = items["IDNRK"].astype(str).str.strip()
        result["site_id"] = _safe_col(items, "PARENT_WERKS", "").astype(str).str.strip()
        comp_qty = pd.to_numeric(_safe_col(items, "MENGE", 1), errors="coerce").fillna(1)
        base_qty = pd.to_numeric(_safe_col(items, "BMENG", 1), errors="coerce").fillna(1).replace(0, 1)
        result["component_quantity"] = comp_qty / base_qty
        result["component_uom"] = _safe_col(items, "MEINS", "EA").astype(str).str.strip()
        result["scrap_percentage"] = pd.to_numeric(_safe_col(items, "AUSCH", 0), errors="coerce").fillna(0)
        result["alternate_group"] = pd.to_numeric(_safe_col(items, "STLAL", 1), errors="coerce").fillna(1).astype(int)
        result["priority"] = pd.to_numeric(_safe_col(items, "POSNR", 1), errors="coerce").fillna(1).astype(int)
        item_cat = _safe_col(items, "POSTP", "L").astype(str).str.strip()
        result["is_active"] = item_cat.isin(["L", "N", ""]).map({True: "true", False: "false"})
        # is_key_material: stock items (POSTP='L') are key materials
        result["is_key_material"] = item_cat.isin(["L"]).map({True: "true", False: "false"})
        result["source"] = "SAP_STPO"
        result = result[result["product_id"].str.len() > 0]
        logger.info(f"Mapped {len(result)} BOM item records")
        return result

    def map_s4hana_pir_to_forecasts(
        self, pbim_df: pd.DataFrame, pbed_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """Map S/4HANA Planned Independent Requirements (PBIM/PBED) to Forecast.

        Enriches with customer_id from PBIM.KDAUF (customer-specific PIRs).
        """
        logger.info("Mapping S/4HANA PIR (PBIM/PBED) to Forecast")
        if pbed_df.empty:
            return pd.DataFrame()
        if not pbim_df.empty:
            # Handle both canonical SAP column name (BDZEI) and HANA variant (BESSION)
            pir_key = "BDZEI" if "BDZEI" in pbim_df.columns else ("BESSION" if "BESSION" in pbim_df.columns else None)
            hcols = [c for c in [pir_key, "MATNR", "WERKS", "KDAUF"] if c and c in pbim_df.columns]
            if pir_key and pir_key in pbim_df.columns and pir_key in pbed_df.columns:
                merged = pbed_df.merge(pbim_df[hcols].drop_duplicates(), on=pir_key, how="left")
            else:
                merged = pbed_df.copy()
        else:
            merged = pbed_df.copy()
        result = pd.DataFrame()
        result["product_id"] = _safe_col(merged, "MATNR", "").astype(str).str.strip()
        result["site_id"] = _safe_col(merged, "WERKS", "").astype(str).str.strip()
        result["forecast_date"] = pd.to_datetime(_safe_col(merged, "PDATU", None), format="%Y%m%d", errors="coerce")
        result["forecast_quantity"] = pd.to_numeric(_safe_col(merged, "PLNMG", 0), errors="coerce").fillna(0)
        result["forecast_type"] = "statistical"
        result["forecast_level"] = "product"
        result["forecast_method"] = "sap_pir"
        result["forecast_version"] = _safe_col(merged, "VERSB", "00").astype(str).str.strip()
        # Customer-specific PIRs have KDAUF (sales order reference) → derive customer
        result["customer_id"] = _safe_col(merged, "KDAUF", "").astype(str).str.strip()
        result["source"] = "SAP_PIR"
        result = result[(result["forecast_quantity"] > 0) & (result["product_id"].str.len() > 0)]
        logger.info(f"Mapped {len(result)} PIR records to Forecast")
        return result

    # ==========================================================================
    # Phase 3 Staging Mappings — New Entity Mappers
    # ==========================================================================

    def map_product_hierarchy(
        self,
        t179_df: pd.DataFrame,
        t179t_df: pd.DataFrame = None,
    ) -> pd.DataFrame:
        """
        Map SAP product hierarchy (T179/T179T) to ProductHierarchy.

        T179 contains the hierarchy structure (PRODH levels).
        T179T contains language-dependent descriptions.
        The PRODH key has a 5+5+8 character structure:
          - Level 1 (category): chars 1-5
          - Level 2 (family): chars 6-10
          - Level 3 (product group): chars 11-18
        """
        logger.info("Mapping T179/T179T to ProductHierarchy")

        if t179_df.empty:
            return pd.DataFrame()

        t179 = t179_df.copy()
        t179["PRODH"] = t179["PRODH"].astype(str).str.strip()

        # Join descriptions from T179T (language = EN preferred)
        if t179t_df is not None and not t179t_df.empty:
            t179t = t179t_df.copy()
            t179t["PRODH"] = t179t["PRODH"].astype(str).str.strip()
            # Prefer English descriptions
            en_desc = t179t[t179t["SPRAS"].astype(str).str.strip().str.upper() == "E"]
            if en_desc.empty:
                en_desc = t179t.drop_duplicates(subset=["PRODH"], keep="first")
            else:
                en_desc = en_desc.drop_duplicates(subset=["PRODH"], keep="first")
            t179 = t179.merge(en_desc[["PRODH", "VTEXT"]], on="PRODH", how="left")
        else:
            t179["VTEXT"] = ""

        result = pd.DataFrame()
        result["id"] = t179["PRODH"]
        result["description"] = _safe_col(t179, "VTEXT", "").astype(str).str.strip()

        # Determine level and parent from PRODH length
        prodh_len = t179["PRODH"].str.len()
        result["level"] = 3  # default
        result.loc[prodh_len <= 5, "level"] = 1
        result.loc[(prodh_len > 5) & (prodh_len <= 10), "level"] = 2

        # Parent: level 2 parent is chars 1-5, level 3 parent is chars 1-10
        result["parent_product_group_id"] = None
        mask_l2 = result["level"] == 2
        mask_l3 = result["level"] == 3
        result.loc[mask_l2, "parent_product_group_id"] = t179.loc[mask_l2, "PRODH"].str[:5].str.strip()
        result.loc[mask_l3, "parent_product_group_id"] = t179.loc[mask_l3, "PRODH"].str[:10].str.strip()

        result["is_active"] = "true"
        result["sort_order"] = range(1, len(result) + 1)

        logger.info(f"Mapped {len(result)} product hierarchy nodes")
        return result

    def map_process_operations(
        self,
        plko_df: pd.DataFrame,
        plpo_df: pd.DataFrame,
        marc_df: pd.DataFrame = None,
    ) -> dict:
        """
        Map routings (PLKO/PLPO) to ProcessHeader + ProcessOperation + ProcessProduct.

        Returns a dict with keys 'headers', 'operations', 'products'.
        """
        logger.info("Mapping PLKO/PLPO to ProcessHeader/ProcessOperation/ProcessProduct")

        if plpo_df.empty:
            return {"headers": pd.DataFrame(), "operations": pd.DataFrame(), "products": pd.DataFrame()}

        # --- ProcessHeader: one per routing (PLNNR + PLNAL) ---
        if not plko_df.empty:
            hdr_src = plko_df.copy()
        else:
            hdr_src = plpo_df[["PLNTY", "PLNNR"]].drop_duplicates()

        headers = pd.DataFrame()
        headers["id"] = hdr_src["PLNNR"].astype(str).str.strip() + "-" + _safe_col(hdr_src, "PLNAL", "1").astype(str).str.strip()
        headers["process_id"] = hdr_src["PLNNR"].astype(str).str.strip()
        headers["description"] = "Routing " + hdr_src["PLNNR"].astype(str).str.strip()
        headers["version"] = pd.to_numeric(_safe_col(hdr_src, "PLNAL", 1), errors="coerce").fillna(1).astype(int)
        headers["status"] = "ACTIVE"
        headers["source"] = "SAP_PLKO"
        headers = headers.drop_duplicates(subset=["id"])

        # --- ProcessOperation: one per operation step ---
        if not plko_df.empty:
            merged = plpo_df.merge(
                plko_df[["PLNTY", "PLNNR", "PLNAL", "WERKS"]].drop_duplicates(),
                on=["PLNTY", "PLNNR"],
                how="left",
            )
        else:
            merged = plpo_df.copy()

        ops = pd.DataFrame()
        ops["header_id"] = merged["PLNNR"].astype(str).str.strip() + "-" + _safe_col(merged, "PLNAL", "1").astype(str).str.strip()
        ops["operation_number"] = pd.to_numeric(_safe_col(merged, "VORNR", _safe_col(merged, "PLNKN", 0)), errors="coerce").fillna(0).astype(int)
        ops["operation_name"] = _safe_col(merged, "LTXA1", "").astype(str).str.strip()
        # Fall back to "Op N" if no description text available
        ops.loc[ops["operation_name"] == "", "operation_name"] = "Op " + ops.loc[ops["operation_name"] == "", "operation_number"].astype(str)
        ops["work_center_id"] = _safe_col(merged, "ARBPL", _safe_col(merged, "ARBID", "")).astype(str).str.strip()
        ops["setup_time"] = pd.to_numeric(_safe_col(merged, "VGW01", 0), errors="coerce").fillna(0)
        ops["run_time_per_unit"] = pd.to_numeric(_safe_col(merged, "VGW02", 0), errors="coerce").fillna(0)
        ops["teardown_time"] = 0.0
        ops["queue_time"] = 0.0
        ops["move_time"] = 0.0
        base_qty = pd.to_numeric(_safe_col(merged, "BMSCH", 1), errors="coerce").fillna(1).replace(0, 1)
        ops["max_units_per_hour"] = (60.0 / ops["run_time_per_unit"].replace(0, np.nan) * base_qty).where(ops["run_time_per_unit"] > 0, np.nan)
        ops["yield_percentage"] = 100.0
        ops["scrap_percentage"] = 0.0

        # Check STEUS (control key) for subcontracting: L = subcontracting
        steus = _safe_col(merged, "STEUS", "").astype(str).str.strip()
        ops["is_subcontracted"] = steus.str.upper().isin(["L", "LOHN"])
        ops["vendor_id"] = ""
        ops["source"] = "SAP_PLPO"

        # --- ProcessProduct: material assignment from MARC (material→routing link) ---
        products = pd.DataFrame()
        if marc_df is not None and not marc_df.empty and "STLNR" in marc_df.columns:
            # Materials linked to routings via PLNNR in MAPL or via BOM assignment
            # For now, create an output product entry per header using MARC material data
            mat_rout = marc_df[["MATNR", "WERKS"]].drop_duplicates()
            if not plko_df.empty and "WERKS" in plko_df.columns:
                linked = mat_rout.merge(
                    plko_df[["PLNNR", "PLNAL", "WERKS"]].drop_duplicates(),
                    on="WERKS",
                    how="inner",
                )
                if not linked.empty:
                    products["header_id"] = linked["PLNNR"].astype(str).str.strip() + "-" + _safe_col(linked, "PLNAL", "1").astype(str).str.strip()
                    products["product_id"] = linked["MATNR"].astype(str).str.strip()
                    products["product_type"] = "output"
                    products["quantity"] = 1.0
                    products["uom"] = "EA"
                    products["source"] = "SAP_MARC"

        logger.info(f"Mapped {len(headers)} process headers, {len(ops)} operations, {len(products)} products")
        return {"headers": headers, "operations": ops, "products": products}

    def map_customer_costs(
        self,
        konv_df: pd.DataFrame,
        vbak_df: pd.DataFrame = None,
        vbap_df: pd.DataFrame = None,
    ) -> pd.DataFrame:
        """
        Map SAP pricing conditions (KONV) to CustomerCost.

        KONV stores condition records from sales orders. Key condition types:
        - PR00: Gross price
        - K004/K005/K007: Material/customer discounts
        - MWST: Tax
        - KF00: Freight
        """
        logger.info("Mapping KONV to CustomerCost")

        if konv_df.empty:
            return pd.DataFrame()

        konv = konv_df.copy()

        # Filter to pricing-relevant condition types
        pricing_types = {"PR00", "PR01", "PR02", "K004", "K005", "K007", "KF00", "HA00", "HB00", "MWST"}
        kschl = _safe_col(konv, "KSCHL", "").astype(str).str.strip()
        konv = konv[kschl.isin(pricing_types)]

        if konv.empty:
            return pd.DataFrame()

        # Map condition type to cost_type
        cost_type_map = {
            "PR00": "unit_price", "PR01": "unit_price", "PR02": "unit_price",
            "K004": "discount", "K005": "discount", "K007": "discount",
            "HA00": "discount", "HB00": "discount",
            "KF00": "freight", "MWST": "tax",
        }

        result = pd.DataFrame()
        # Link back to sales order for customer/product context
        if vbak_df is not None and not vbak_df.empty and "KNUMV" in konv.columns:
            # KNUMV links KONV to VBAK
            konv_with_order = konv.merge(
                vbak_df[["KNUMV", "KUNNR", "VBELN"]].drop_duplicates(),
                on="KNUMV",
                how="left",
            )
            result["customer_id"] = _safe_col(konv_with_order, "KUNNR", "").astype(str).str.strip()
            result["order_id"] = _safe_col(konv_with_order, "VBELN", "").astype(str).str.strip()
        else:
            konv_with_order = konv
            result["customer_id"] = ""
            result["order_id"] = ""

        # Product + site from VBAP join
        if vbap_df is not None and not vbap_df.empty and "VBELN" in konv_with_order.columns:
            vbap_cols = ["VBELN", "POSNR", "MATNR", "WERKS"]
            vbap_lookup = vbap_df[[c for c in vbap_cols if c in vbap_df.columns]].drop_duplicates()
            vbap_lookup["VBELN"] = vbap_lookup["VBELN"].astype(str).str.strip()
            vbap_lookup["POSNR"] = vbap_lookup["POSNR"].astype(str).str.strip()
            kposn = _safe_col(konv_with_order, "KPOSN", "").astype(str).str.strip()
            konv_with_order = konv_with_order.copy()
            konv_with_order["_POSNR"] = kposn
            konv_with_order["_VBELN"] = _safe_col(konv_with_order, "VBELN", "").astype(str).str.strip()
            konv_with_order = konv_with_order.merge(
                vbap_lookup, left_on=["_VBELN", "_POSNR"], right_on=["VBELN", "POSNR"],
                how="left", suffixes=("", "_vbap"),
            )
            result["product_id"] = _safe_col(konv_with_order, "MATNR_vbap", _safe_col(konv_with_order, "MATNR", "")).astype(str).str.strip()
            result["site_id"] = _safe_col(konv_with_order, "WERKS", "").astype(str).str.strip()
        else:
            result["product_id"] = _safe_col(konv_with_order, "MATNR", "").astype(str).str.strip() if "MATNR" in konv_with_order.columns else ""
            result["site_id"] = ""

        result["cost_type"] = _safe_col(konv_with_order, "KSCHL", "").astype(str).str.strip().map(cost_type_map).fillna("other")
        result["amount"] = pd.to_numeric(_safe_col(konv_with_order, "KBETR", 0), errors="coerce").fillna(0)
        result["currency"] = _safe_col(konv_with_order, "WAERS", "USD").astype(str).str.strip()
        result["uom"] = _safe_col(konv_with_order, "KPEIN", "EA").astype(str)
        result["effective_date"] = pd.to_datetime(_safe_col(konv_with_order, "KDATU", None), errors="coerce")

        # Scale quantities for volume pricing
        result["min_quantity"] = pd.to_numeric(_safe_col(konv_with_order, "KSTBM", 0), errors="coerce").fillna(0)
        result["max_quantity"] = 0.0  # KONV doesn't have explicit max — would need condition scale table

        # Contract reference from SO header
        if "VGBEL" in konv_with_order.columns:
            result["contract_id"] = _safe_col(konv_with_order, "VGBEL", "").astype(str).str.strip()
        else:
            result["contract_id"] = ""

        result["source"] = "SAP_KONV"

        logger.info(f"Mapped {len(result)} customer cost records")
        return result

    def map_supplier_performance(
        self,
        ekbe_df: pd.DataFrame,
        eket_df: pd.DataFrame = None,
        ekpo_df: pd.DataFrame = None,
    ) -> pd.DataFrame:
        """
        Map SAP PO history (EKBE) + schedule lines (EKET) to SupplierPerformance.

        Computes per-vendor monthly metrics:
        - On-time delivery rate (EKBE goods receipt date vs EKET scheduled date)
        - Quality reject rate (EKBE movement type 122 = returns)
        - Average lead time (order date to GR date)
        """
        logger.info("Mapping EKBE/EKET to SupplierPerformance")

        if ekbe_df.empty:
            return pd.DataFrame()

        ekbe = ekbe_df.copy()
        # Filter to goods receipt entries (VGABE=1 or BEWTP=E)
        if "VGABE" in ekbe.columns:
            gr_mask = ekbe["VGABE"].astype(str).str.strip() == "1"
        elif "BEWTP" in ekbe.columns:
            gr_mask = ekbe["BEWTP"].astype(str).str.strip() == "E"
        else:
            gr_mask = pd.Series(True, index=ekbe.index)

        gr_entries = ekbe[gr_mask].copy()
        if gr_entries.empty:
            return pd.DataFrame()

        # Need vendor from EKPO
        if ekpo_df is not None and not ekpo_df.empty:
            # Get vendor (LIFNR) from EKKO via EKPO, or directly if LIFNR in EKPO
            vendor_cols = ["EBELN", "EBELP"]
            if "LIFNR" in ekpo_df.columns:
                vendor_cols.append("LIFNR")
            gr_entries = gr_entries.merge(
                ekpo_df[vendor_cols].drop_duplicates(),
                on=["EBELN", "EBELP"],
                how="left",
            )

        if "LIFNR" not in gr_entries.columns:
            logger.warning("No LIFNR available in EKBE/EKPO — cannot compute supplier performance")
            return pd.DataFrame()

        gr_entries["LIFNR"] = gr_entries["LIFNR"].astype(str).str.strip()
        gr_entries["gr_date"] = pd.to_datetime(_safe_col(gr_entries, "BUDAT", _safe_col(gr_entries, "BLDAT", None)), errors="coerce")
        gr_entries["gr_qty"] = pd.to_numeric(_safe_col(gr_entries, "MENGE", 0), errors="coerce").fillna(0)

        # Join EKET for scheduled delivery date
        if eket_df is not None and not eket_df.empty:
            eket_first = eket_df.sort_values("ETENR").drop_duplicates(subset=["EBELN", "EBELP"], keep="first")
            gr_entries = gr_entries.merge(
                eket_first[["EBELN", "EBELP", "EINDT"]],
                on=["EBELN", "EBELP"],
                how="left",
            )
            gr_entries["sched_date"] = pd.to_datetime(gr_entries["EINDT"], errors="coerce")
        else:
            gr_entries["sched_date"] = pd.NaT

        # Compute monthly period
        gr_entries["period"] = gr_entries["gr_date"].dt.to_period("M")
        gr_entries = gr_entries.dropna(subset=["period"])

        # Aggregate per vendor per month
        grouped = gr_entries.groupby(["LIFNR", "period"])

        records = []
        for (vendor, period), grp in grouped:
            total_orders = len(grp)
            total_qty = grp["gr_qty"].sum()

            # On-time: GR date <= scheduled date
            has_sched = grp["sched_date"].notna()
            if has_sched.any():
                on_time = ((grp.loc[has_sched, "gr_date"] <= grp.loc[has_sched, "sched_date"]).sum())
                late = has_sched.sum() - on_time
                days_late_series = (grp.loc[has_sched, "gr_date"] - grp.loc[has_sched, "sched_date"]).dt.days
                avg_days_late = days_late_series.clip(lower=0).mean()
            else:
                on_time = 0
                late = 0
                avg_days_late = None

            # Total spend from EKBE.DMBTR (document amount in local currency)
            spend = pd.to_numeric(_safe_col(grp, "DMBTR", 0), errors="coerce").sum()

            # Quality rejections: BWART 122 = return to vendor
            if "BWART" in grp.columns:
                returns = grp[grp["BWART"].astype(str).str.strip() == "122"]
                rejected_qty = pd.to_numeric(_safe_col(returns, "MENGE", 0), errors="coerce").sum()
            else:
                rejected_qty = 0

            accepted_qty = max(0, total_qty - rejected_qty)

            records.append({
                "tpartner_id": vendor,
                "period_start": period.start_time,
                "period_end": period.end_time,
                "period_type": "MONTHLY",
                "orders_placed": total_orders,
                "orders_delivered_on_time": on_time,
                "orders_delivered_late": late,
                "average_days_late": avg_days_late,
                "units_received": int(total_qty),
                "units_accepted": int(accepted_qty),
                "units_rejected": int(rejected_qty),
                "on_time_delivery_rate": (on_time / has_sched.sum() * 100) if has_sched.sum() > 0 else None,
                "total_spend": float(spend),
                "currency": "USD",
            })

        result = pd.DataFrame(records)
        if not result.empty:
            logger.info(f"Mapped {len(result)} supplier performance records")
        return result

    def map_production_capacity(
        self,
        crhd_df: pd.DataFrame,
        kako_df: pd.DataFrame = None,
    ) -> pd.DataFrame:
        """
        Map SAP work centers (CRHD) + capacity headers (KAKO) to ProductionCapacity.

        CRHD: Work center master (ARBPL, WERKS, VERWE=capacity category)
        KAKO: Capacity header (KAESSION, ANESSION, ENDDA, capacity values)
        """
        logger.info("Mapping CRHD/KAKO to ProductionCapacity")

        if crhd_df.empty:
            return pd.DataFrame()

        crhd = crhd_df.copy()
        crhd["ARBPL"] = crhd["ARBPL"].astype(str).str.strip()
        crhd["WERKS"] = _safe_col(crhd, "WERKS", "").astype(str).str.strip()

        result = pd.DataFrame()

        if kako_df is not None and not kako_df.empty:
            # Join capacity data via OBJID (CRHD.OBJID = KAKO.OBJID or via ARBPL)
            if "OBJID" in crhd.columns and "OBJID" in kako_df.columns:
                merged = crhd.merge(kako_df, on="OBJID", how="left", suffixes=("", "_kako"))
            else:
                merged = crhd
        else:
            merged = crhd

        result["site_id"] = merged["WERKS"]
        result["work_center_id"] = merged["ARBPL"]
        result["capacity_type"] = "production"
        result["capacity_period"] = "day"

        # Available capacity from KAKO or default
        if "ANESSION" in merged.columns:
            result["max_capacity_per_period"] = pd.to_numeric(
                _safe_col(merged, "ANESSION", 480), errors="coerce"
            ).fillna(480)  # Default 8h = 480 min
        else:
            result["max_capacity_per_period"] = 480.0

        result["capacity_uom"] = "MINUTES"
        result["current_capacity_used"] = 0.0

        if "ENDDA" in merged.columns:
            result["effective_end_date"] = pd.to_datetime(merged["ENDDA"], errors="coerce")
        if "DATUB" in merged.columns:
            result["effective_start_date"] = pd.to_datetime(merged["DATUB"], errors="coerce")

        result["source"] = "SAP_CRHD"
        result = result.drop_duplicates(subset=["site_id", "work_center_id"])

        logger.info(f"Mapped {len(result)} production capacity records")
        return result

    def map_fulfillment_orders(
        self,
        likp_df: pd.DataFrame,
        lips_df: pd.DataFrame,
        ltak_df: pd.DataFrame = None,
        ltap_df: pd.DataFrame = None,
    ) -> pd.DataFrame:
        """
        Map SAP deliveries (LIKP/LIPS) + warehouse tasks (LTAK/LTAP) to FulfillmentOrder.

        Combines delivery header/item info with pick/pack/ship status from WM tasks.
        """
        logger.info("Mapping LIKP/LIPS/LTAK/LTAP to FulfillmentOrder")

        if lips_df.empty:
            return pd.DataFrame()

        # Merge delivery header + items
        header_cols = ["VBELN"]
        for col in ["KUNNR", "LFDAT", "WADAT_IST", "LDDAT", "BOLNR", "LIFNR"]:
            if col in likp_df.columns:
                header_cols.append(col)

        merged = lips_df.merge(likp_df[header_cols], on="VBELN", how="left")

        result = pd.DataFrame()
        result["fulfillment_order_id"] = merged["VBELN"].astype(str).str.strip() + "-" + merged["POSNR"].astype(str).str.strip()
        result["order_id"] = _safe_col(merged, "VGBEL", merged["VBELN"]).astype(str).str.strip()  # Reference SO
        result["order_line_id"] = _safe_col(merged, "VGPOS", merged["POSNR"]).astype(str).str.strip()
        result["product_id"] = merged["MATNR"].astype(str).str.strip()
        result["site_id"] = merged["WERKS"].astype(str).str.strip()
        result["quantity"] = pd.to_numeric(_safe_col(merged, "LFIMG", 0), errors="coerce").fillna(0)
        result["uom"] = _safe_col(merged, "VRKME", "EA").astype(str).str.strip()
        result["customer_id"] = _safe_col(merged, "KUNNR", "").astype(str).str.strip()
        result["promised_date"] = pd.to_datetime(_safe_col(merged, "LFDAT", None), errors="coerce")
        result["ship_date"] = pd.to_datetime(_safe_col(merged, "WADAT_IST", None), errors="coerce")
        result["delivery_date"] = pd.to_datetime(_safe_col(merged, "LDDAT", None), errors="coerce")
        result["tracking_number"] = _safe_col(merged, "BOLNR", "").astype(str).str.strip()
        result["carrier"] = _safe_col(merged, "LIFNR", "").astype(str).str.strip()

        result["shipped_quantity"] = result["quantity"]
        result["allocated_quantity"] = result["quantity"]

        # Status determination
        has_ship = result["ship_date"].notna()
        has_delivery = result["delivery_date"].notna()
        result["status"] = "CREATED"
        result.loc[has_ship, "status"] = "SHIPPED"
        result.loc[has_delivery, "status"] = "DELIVERED"

        # Enrich with warehouse task data (pick/pack)
        if ltak_df is not None and not ltak_df.empty and ltap_df is not None and not ltap_df.empty:
            # LTAK has warehouse task headers linked to delivery via VBELN
            if "VBELN" in ltak_df.columns:
                wm_tasks = ltak_df.merge(ltap_df, on=["TESSION", "TAESSION"], how="inner") if "TESSION" in ltak_df.columns and "TESSION" in ltap_df.columns else pd.DataFrame()
                if not wm_tasks.empty and "VBELN" in wm_tasks.columns:
                    # Get earliest pick date per delivery
                    wm_tasks["pick_dt"] = pd.to_datetime(_safe_col(wm_tasks, "BDATU", None), errors="coerce")
                    pick_dates = wm_tasks.groupby("VBELN")["pick_dt"].min().reset_index()
                    pick_dates = pick_dates.rename(columns={"pick_dt": "_pick_date"})
                    result = result.merge(
                        pick_dates.rename(columns={"VBELN": "_vbeln"}),
                        left_on=result["fulfillment_order_id"].str.split("-").str[0],
                        right_on="_vbeln",
                        how="left",
                    )
                    if "_pick_date" in result.columns:
                        result["pick_date"] = result["_pick_date"]
                        result = result.drop(columns=["_pick_date", "_vbeln"], errors="ignore")

        result["delivered_quantity"] = result["quantity"].where(has_delivery, 0.0)
        result["short_quantity"] = (result["quantity"] - result["shipped_quantity"]).clip(lower=0)
        result["ship_method"] = _safe_col(merged, "VSART", "").astype(str).str.strip() if "VSART" in merged.columns else ""

        # Wave ID from LTAK
        if ltak_df is not None and not ltak_df.empty and "BENUM" in ltak_df.columns:
            wave_map = ltak_df[["BENUM", "LGNUM", "TANUM"]].drop_duplicates(subset=["BENUM"], keep="first")
            wave_map["BENUM"] = wave_map["BENUM"].astype(str).str.strip()
            wave_map["_wave"] = wave_map["LGNUM"].astype(str).str.strip() + "-" + wave_map["TANUM"].astype(str).str.strip()
            wave_dict = wave_map.set_index("BENUM")["_wave"].to_dict()
            result["wave_id"] = result["fulfillment_order_id"].str.split("-").str[0].map(wave_dict).fillna("")
        else:
            result["wave_id"] = ""

        # Pick location from LTAP (source storage bin)
        if ltap_df is not None and not ltap_df.empty and "VLPLA" in ltap_df.columns:
            pick_loc = ltap_df[["MATNR", "VLPLA"]].copy()
            pick_loc["MATNR"] = pick_loc["MATNR"].astype(str).str.strip()
            pick_loc = pick_loc.drop_duplicates(subset=["MATNR"], keep="first")
            pick_dict = pick_loc.set_index("MATNR")["VLPLA"].to_dict()
            result["pick_location"] = result["product_id"].map(pick_dict).fillna("")
        else:
            result["pick_location"] = ""

        result["source"] = "SAP_LIKP_LIPS"
        result["priority"] = 3

        logger.info(f"Mapped {len(result)} fulfillment order records")
        return result

    def map_backorders(
        self,
        vbak_df: pd.DataFrame,
        vbap_df: pd.DataFrame,
        vbup_df: pd.DataFrame = None,
        vbep_df: pd.DataFrame = None,
        lips_df: pd.DataFrame = None,
    ) -> pd.DataFrame:
        """
        Map incomplete sales orders to Backorder.

        A backorder = SO line where ordered_qty > confirmed_qty (from VBEP.BMENG)
        or where VBUP item status indicates incomplete delivery.
        """
        logger.info("Mapping VBAK/VBAP/VBUP/VBEP to Backorder")

        if vbap_df.empty:
            return pd.DataFrame()

        # Merge headers
        items = vbap_df.merge(
            vbak_df[["VBELN", "KUNNR", "ERDAT"]],
            on="VBELN",
            how="left",
        )

        # Join VBEP for confirmed qty
        if vbep_df is not None and not vbep_df.empty:
            vbep_agg = vbep_df.groupby(["VBELN", "POSNR"]).agg(
                confirmed_qty=("BMENG", lambda x: pd.to_numeric(x, errors="coerce").sum()),
                earliest_date=("EDATU", "min"),
            ).reset_index()
            items = items.merge(vbep_agg, on=["VBELN", "POSNR"], how="left")
        else:
            items["confirmed_qty"] = 0
            items["earliest_date"] = None

        # Join VBUP for item-level delivery status
        if vbup_df is not None and not vbup_df.empty:
            vbup_cols = ["VBELN", "POSNR"]
            if "LFSTA" in vbup_df.columns:
                vbup_cols.append("LFSTA")  # Delivery status
            if "GBSTA" in vbup_df.columns:
                vbup_cols.append("GBSTA")  # Overall processing status
            items = items.merge(vbup_df[vbup_cols].drop_duplicates(), on=["VBELN", "POSNR"], how="left")

        ordered_qty = pd.to_numeric(items["KWMENG"], errors="coerce").fillna(0)
        confirmed = pd.to_numeric(_safe_col(items, "confirmed_qty", 0), errors="coerce").fillna(0)
        backorder_qty = (ordered_qty - confirmed).clip(lower=0)

        # Filter to lines with actual backorder quantity
        has_backorder = backorder_qty > 0

        # Also include items where VBUP.LFSTA indicates incomplete (A or B)
        if "LFSTA" in items.columns:
            incomplete = items["LFSTA"].astype(str).str.strip().isin(["A", "B", ""])
            has_backorder = has_backorder | (incomplete & (ordered_qty > 0))

        bo_items = items[has_backorder].copy()
        bo_qty = backorder_qty[has_backorder]

        if bo_items.empty:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["backorder_id"] = "BO-" + bo_items["VBELN"].astype(str).str.strip() + "-" + bo_items["POSNR"].astype(str).str.strip()
        result["order_id"] = bo_items["VBELN"].astype(str).str.strip()
        result["product_id"] = bo_items["MATNR"].astype(str).str.strip()
        result["site_id"] = bo_items["WERKS"].astype(str).str.strip()
        result["customer_id"] = _safe_col(bo_items, "KUNNR", "").astype(str).str.strip()
        result["backorder_quantity"] = bo_qty.values
        result["allocated_quantity"] = confirmed[has_backorder].values
        # Fulfilled quantity from LIPS (deliveries against this SO)
        if lips_df is not None and not lips_df.empty and "VGBEL" in lips_df.columns:
            lips_agg = lips_df.copy()
            lips_agg["VGBEL"] = lips_agg["VGBEL"].astype(str).str.strip()
            lips_agg["VGPOS"] = lips_agg["VGPOS"].astype(str).str.strip()
            lips_agg["_qty"] = pd.to_numeric(_safe_col(lips_agg, "LFIMG", 0), errors="coerce").fillna(0)
            ful_agg = lips_agg.groupby(["VGBEL", "VGPOS"])["_qty"].sum().reset_index()
            ful_agg["_key"] = ful_agg["VGBEL"] + "|" + ful_agg["VGPOS"]
            ful_dict = ful_agg.set_index("_key")["_qty"].to_dict()
            bo_key = bo_items["VBELN"].astype(str).str.strip() + "|" + bo_items["POSNR"].astype(str).str.strip()
            result["fulfilled_quantity"] = bo_key.map(ful_dict).fillna(0).values
        else:
            result["fulfilled_quantity"] = 0.0
        result["status"] = "CREATED"
        result["requested_delivery_date"] = pd.to_datetime(
            _safe_col(bo_items, "earliest_date", None), errors="coerce"
        )
        result["created_date"] = pd.to_datetime(bo_items["ERDAT"], errors="coerce")
        result["priority"] = 3
        result["priority_code"] = "STANDARD"

        # Aging = days since order creation
        now = pd.Timestamp.now()
        result["aging_days"] = (now - result["created_date"]).dt.days.fillna(0).astype(int)

        logger.info(f"Mapped {len(result)} backorder records")
        return result

    def map_inbound_orders(
        self,
        ekko_df: pd.DataFrame,
        ekpo_df: pd.DataFrame,
        eket_df: pd.DataFrame = None,
        ekbe_df: pd.DataFrame = None,
        lfa1_df: pd.DataFrame = None,
    ) -> dict:
        """
        Map SAP purchase orders (EKKO/EKPO/EKET/EKBE) to InboundOrder + InboundOrderLine + InboundOrderLineSchedule.

        Returns dict with keys 'orders', 'lines', 'schedules'.
        """
        logger.info("Mapping EKKO/EKPO/EKET/EKBE to InboundOrder/InboundOrderLine/Schedule")

        if ekpo_df.empty:
            return {"orders": pd.DataFrame(), "lines": pd.DataFrame(), "schedules": pd.DataFrame()}

        # --- InboundOrder (header level from EKKO) ---
        orders = pd.DataFrame()
        if not ekko_df.empty:
            orders["id"] = ekko_df["EBELN"].astype(str).str.strip()
            orders["order_type"] = _safe_col(ekko_df, "BSART", "NB").astype(str).str.strip()
            orders["supplier_id"] = _safe_col(ekko_df, "LIFNR", "").astype(str).str.strip()
            orders["order_date"] = pd.to_datetime(_safe_col(ekko_df, "BEDAT", None), errors="coerce")
            orders["currency"] = _safe_col(ekko_df, "WAERS", "USD").astype(str).str.strip()
            orders["reference_number"] = _safe_col(ekko_df, "IHREZ", "").astype(str).str.strip() if "IHREZ" in ekko_df.columns else ""
            orders["contract_id"] = _safe_col(ekko_df, "KONNR", "").astype(str).str.strip() if "KONNR" in ekko_df.columns else ""
            orders["status"] = "OPEN"

            # Supplier name from LFA1 join
            if lfa1_df is not None and not lfa1_df.empty:
                name_map = lfa1_df[["LIFNR", "NAME1"]].copy()
                name_map["LIFNR"] = name_map["LIFNR"].astype(str).str.strip()
                name_dict = name_map.drop_duplicates(subset=["LIFNR"]).set_index("LIFNR")["NAME1"].to_dict()
                orders["supplier_name"] = orders["supplier_id"].map(name_dict).fillna("")
            else:
                orders["supplier_name"] = ""

            orders["source"] = "SAP_EKKO"
        else:
            # Derive headers from EKPO
            hdr = ekpo_df[["EBELN"]].drop_duplicates()
            orders["id"] = hdr["EBELN"].astype(str).str.strip()
            orders["order_type"] = "NB"
            orders["order_date"] = pd.NaT
            orders["status"] = "OPEN"
            orders["supplier_name"] = ""
            orders["reference_number"] = ""
            orders["contract_id"] = ""
            orders["source"] = "SAP_EKPO"

        # --- InboundOrderLine ---
        lines = pd.DataFrame()
        lines["order_id"] = ekpo_df["EBELN"].astype(str).str.strip()
        lines["line_number"] = pd.to_numeric(ekpo_df["EBELP"], errors="coerce").fillna(0).astype(int)
        lines["product_id"] = ekpo_df["MATNR"].astype(str).str.strip()
        lines["site_id"] = _safe_col(ekpo_df, "WERKS", "").astype(str).str.strip()
        lines["ordered_quantity"] = pd.to_numeric(_safe_col(ekpo_df, "MENGE", 0), errors="coerce").fillna(0)
        lines["unit_price"] = pd.to_numeric(_safe_col(ekpo_df, "NETPR", 0), errors="coerce").fillna(0)
        lines["uom"] = _safe_col(ekpo_df, "MEINS", "EA").astype(str).str.strip()
        lines["status"] = "OPEN"
        lines["source"] = "SAP_EKPO"

        # Compute received_quantity from EKBE if available
        if ekbe_df is not None and not ekbe_df.empty:
            # Filter to goods receipts
            if "VGABE" in ekbe_df.columns:
                gr = ekbe_df[ekbe_df["VGABE"].astype(str).str.strip() == "1"]
            elif "BEWTP" in ekbe_df.columns:
                gr = ekbe_df[ekbe_df["BEWTP"].astype(str).str.strip() == "E"]
            else:
                gr = ekbe_df
            if not gr.empty:
                gr_qty = gr.groupby(["EBELN", "EBELP"])["MENGE"].apply(
                    lambda x: pd.to_numeric(x, errors="coerce").sum()
                ).reset_index()
                gr_qty = gr_qty.rename(columns={"MENGE": "_received"})
                gr_qty["EBELN"] = gr_qty["EBELN"].astype(str).str.strip()
                gr_qty["EBELP"] = gr_qty["EBELP"].astype(str).str.strip()
                lines = lines.merge(
                    gr_qty,
                    left_on=["order_id", lines["line_number"].astype(str)],
                    right_on=["EBELN", "EBELP"],
                    how="left",
                )
                lines["received_quantity"] = _safe_col(lines, "_received", 0)
                lines = lines.drop(columns=["EBELN", "EBELP", "_received", "key_1"], errors="ignore")
            else:
                lines["received_quantity"] = 0.0
        else:
            lines["received_quantity"] = 0.0

        lines["open_quantity"] = (lines["ordered_quantity"] - lines["received_quantity"]).clip(lower=0)

        # Update header totals + delivery dates + total_value
        if not orders.empty:
            agg_dict = {
                "ordered_quantity": "sum",
                "received_quantity": "sum",
                "unit_price": lambda x: (x * lines.loc[x.index, "ordered_quantity"]).sum(),  # total value
            }
            order_totals = lines.groupby("order_id").agg(
                total_ordered_qty=("ordered_quantity", "sum"),
                total_received_qty=("received_quantity", "sum"),
            ).reset_index()
            # Total value = sum(unit_price * ordered_quantity) per order
            lines["_line_value"] = lines["unit_price"] * lines["ordered_quantity"]
            order_value = lines.groupby("order_id")["_line_value"].sum().reset_index()
            order_value = order_value.rename(columns={"_line_value": "total_value"})
            lines = lines.drop(columns=["_line_value"])
            orders = orders.merge(order_totals, left_on="id", right_on="order_id", how="left")
            orders = orders.drop(columns=["order_id"], errors="ignore")
            orders = orders.merge(order_value, left_on="id", right_on="order_id", how="left")
            orders = orders.drop(columns=["order_id"], errors="ignore")

            # Delivery dates from EKET (earliest/latest schedule)
            if eket_df is not None and not eket_df.empty:
                sched_dates = eket_df.copy()
                sched_dates["EINDT"] = pd.to_datetime(sched_dates["EINDT"], errors="coerce")
                date_agg = sched_dates.groupby("EBELN")["EINDT"].agg(["min", "max"]).reset_index()
                date_agg = date_agg.rename(columns={"min": "requested_delivery_date", "max": "promised_delivery_date"})
                date_agg["EBELN"] = date_agg["EBELN"].astype(str).str.strip()
                orders = orders.merge(date_agg, left_on="id", right_on="EBELN", how="left")
                orders = orders.drop(columns=["EBELN"], errors="ignore")
            else:
                orders["requested_delivery_date"] = pd.NaT
                orders["promised_delivery_date"] = pd.NaT

            # Actual delivery date from EKBE (latest GR date)
            if ekbe_df is not None and not ekbe_df.empty:
                ekbe_gr = ekbe_df.copy()
                if "VGABE" in ekbe_gr.columns:
                    ekbe_gr = ekbe_gr[ekbe_gr["VGABE"].astype(str).str.strip() == "1"]
                ekbe_gr["BUDAT"] = pd.to_datetime(_safe_col(ekbe_gr, "BUDAT", None), errors="coerce")
                actual_dates = ekbe_gr.groupby("EBELN")["BUDAT"].max().reset_index()
                actual_dates = actual_dates.rename(columns={"BUDAT": "actual_delivery_date"})
                actual_dates["EBELN"] = actual_dates["EBELN"].astype(str).str.strip()
                orders = orders.merge(actual_dates, left_on="id", right_on="EBELN", how="left")
                orders = orders.drop(columns=["EBELN"], errors="ignore")
            else:
                orders["actual_delivery_date"] = pd.NaT

            # Ship-to site from first EKPO line per order
            site_per_order = lines.drop_duplicates(subset=["order_id"], keep="first")[["order_id", "site_id"]]
            site_per_order = site_per_order.rename(columns={"site_id": "ship_to_site_id"})
            orders = orders.merge(site_per_order, left_on="id", right_on="order_id", how="left")
            orders = orders.drop(columns=["order_id"], errors="ignore")

        # --- InboundOrderLineSchedule from EKET ---
        schedules = pd.DataFrame()
        if eket_df is not None and not eket_df.empty:
            schedules["order_id"] = eket_df["EBELN"].astype(str).str.strip()
            schedules["line_number"] = pd.to_numeric(eket_df["EBELP"], errors="coerce").fillna(0).astype(int)
            schedules["schedule_number"] = pd.to_numeric(_safe_col(eket_df, "ETENR", 1), errors="coerce").fillna(1).astype(int)
            schedules["scheduled_quantity"] = pd.to_numeric(_safe_col(eket_df, "MENGE", 0), errors="coerce").fillna(0)
            schedules["received_quantity"] = pd.to_numeric(_safe_col(eket_df, "WEMNG", 0), errors="coerce").fillna(0)
            schedules["scheduled_date"] = pd.to_datetime(_safe_col(eket_df, "EINDT", None), errors="coerce")
            open_sched = schedules["scheduled_quantity"] - schedules["received_quantity"]
            schedules["status"] = "SCHEDULED"
            schedules.loc[open_sched <= 0, "status"] = "RECEIVED"
            schedules["source"] = "SAP_EKET"

        logger.info(f"Mapped {len(orders)} inbound orders, {len(lines)} lines, {len(schedules)} schedules")
        return {"orders": orders, "lines": lines, "schedules": schedules}

    def map_outbound_order_lines(
        self,
        vbak_df: pd.DataFrame,
        vbap_df: pd.DataFrame,
        vbep_df: pd.DataFrame = None,
        vbuk_df: pd.DataFrame = None,
        lips_df: pd.DataFrame = None,
    ) -> pd.DataFrame:
        """
        Map SAP sales orders (VBAK/VBAP) to OutboundOrderLine.

        Enriches with VBEP for delivery dates/confirmed qty and VBUK for status.
        """
        logger.info("Mapping VBAK/VBAP/VBEP/VBUK to OutboundOrderLine")

        if vbap_df.empty:
            return pd.DataFrame()

        # Merge headers + items
        items = vbap_df.merge(
            vbak_df[["VBELN", "KUNNR", "ERDAT"]],
            on="VBELN",
            how="left",
        )

        # Join VBEP for delivery dates and confirmed qty
        if vbep_df is not None and not vbep_df.empty:
            vbep_sorted = vbep_df.sort_values("ETENR")
            vbep_first = vbep_sorted.drop_duplicates(subset=["VBELN", "POSNR"], keep="first")
            sched_cols = ["VBELN", "POSNR"]
            for col in ["EDATU", "BMENG"]:
                if col in vbep_first.columns:
                    sched_cols.append(col)
            items = items.merge(vbep_first[sched_cols], on=["VBELN", "POSNR"], how="left")

        # Join VBUK for document-level status
        if vbuk_df is not None and not vbuk_df.empty:
            if "GBSTK" in vbuk_df.columns:
                items = items.merge(
                    vbuk_df[["VBELN", "GBSTK"]].drop_duplicates(subset=["VBELN"]),
                    on="VBELN",
                    how="left",
                )

        result = pd.DataFrame()
        result["order_id"] = items["VBELN"].astype(str).str.strip()
        result["line_number"] = pd.to_numeric(items["POSNR"], errors="coerce").fillna(0).astype(int)
        result["product_id"] = items["MATNR"].astype(str).str.strip()
        result["site_id"] = items["WERKS"].astype(str).str.strip()
        result["ordered_quantity"] = pd.to_numeric(items["KWMENG"], errors="coerce").fillna(0)
        result["order_date"] = pd.to_datetime(items["ERDAT"], errors="coerce")

        # Delivery dates from VBEP
        if "EDATU" in items.columns:
            result["requested_delivery_date"] = pd.to_datetime(items["EDATU"], errors="coerce")
        else:
            result["requested_delivery_date"] = pd.NaT

        # Promised/confirmed qty from VBEP.BMENG
        if "BMENG" in items.columns:
            result["promised_quantity"] = pd.to_numeric(items["BMENG"], errors="coerce")
        else:
            result["promised_quantity"] = result["ordered_quantity"]

        # Promised delivery date = confirmed delivery from VBEP
        if "EDATU" in items.columns:
            result["promised_delivery_date"] = pd.to_datetime(items["EDATU"], errors="coerce")
        else:
            result["promised_delivery_date"] = pd.NaT

        # Shipped quantity from LIPS (sum of LFIMG per SO/item via VGBEL/VGPOS)
        if lips_df is not None and not lips_df.empty and "VGBEL" in lips_df.columns:
            shipped = lips_df.copy()
            shipped["VGBEL"] = shipped["VGBEL"].astype(str).str.strip()
            shipped["VGPOS"] = shipped["VGPOS"].astype(str).str.strip()
            shipped["_qty"] = pd.to_numeric(_safe_col(shipped, "LFIMG", 0), errors="coerce").fillna(0)
            ship_agg = shipped.groupby(["VGBEL", "VGPOS"])["_qty"].sum().reset_index()
            ship_agg = ship_agg.rename(columns={"_qty": "_shipped"})
            items_key = result["order_id"].astype(str) + "|" + result["line_number"].astype(str)
            ship_agg["_key"] = ship_agg["VGBEL"] + "|" + ship_agg["VGPOS"]
            ship_dict = ship_agg.set_index("_key")["_shipped"].to_dict()
            result["shipped_quantity"] = items_key.map(ship_dict).fillna(0)
        else:
            result["shipped_quantity"] = 0.0

        result["backlog_quantity"] = (result["ordered_quantity"] - result["shipped_quantity"].fillna(0) - result["promised_quantity"].fillna(0)).clip(lower=0)

        # Status from VBUK.GBSTK
        if "GBSTK" in items.columns:
            status_map = {"A": "DRAFT", "B": "PARTIAL", "C": "COMPLETED", "": "DRAFT"}
            result["status"] = items["GBSTK"].fillna("").map(
                lambda x: status_map.get(str(x).strip(), "DRAFT")
            )
        else:
            result["status"] = "DRAFT"

        result["priority_code"] = "STANDARD"
        result["source"] = "SAP_VBAK_VBAP"

        # Customer as market_demand reference
        result["customer_id"] = _safe_col(items, "KUNNR", "").astype(str).str.strip()

        logger.info(f"Mapped {len(result)} outbound order line records")
        return result

    # ==========================================================================
    # Phase 4 Staging Mappings — Remaining Entity Coverage
    # ==========================================================================

    def map_supply_planning_parameters(
        self, marc_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Map MARC MRP controller data to SupplyPlanningParameters.

        MARC.DISPO = MRP controller code (maps to planner_name).
        """
        logger.info("Mapping MARC to SupplyPlanningParameters")

        if marc_df.empty:
            return pd.DataFrame()

        # One entry per product (dedup across plants — take first)
        marc = marc_df.copy()
        marc["MATNR"] = marc["MATNR"].astype(str).str.strip()
        marc = marc.drop_duplicates(subset=["MATNR"], keep="first")

        result = pd.DataFrame()
        result["product_id"] = marc["MATNR"]
        result["planner_name"] = _safe_col(marc, "DISPO", "").astype(str).str.strip()
        result["planner_email"] = ""  # No email in SAP MARC
        result["is_active"] = "true"
        result["source"] = "SAP_MARC"

        # Filter to records that actually have an MRP controller
        result = result[result["planner_name"].str.len() > 0]

        logger.info(f"Mapped {len(result)} supply planning parameter records")
        return result

    def map_reservations(self, resb_df: pd.DataFrame) -> pd.DataFrame:
        """
        Map material reservations (RESB) to Reservation entity.

        Unlike map_reservations_to_allocations (ATP format), this produces the
        proper AWS SC Reservation entity with reservation_date, reserved_quantity,
        reservation_type, and reference_id.
        """
        logger.info("Mapping RESB to Reservation entity")

        if resb_df.empty:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["product_id"] = resb_df["MATNR"].astype(str).str.strip()
        result["site_id"] = resb_df["WERKS"].astype(str).str.strip()
        result["reservation_date"] = pd.to_datetime(
            _safe_col(resb_df, "BDTER", None), format="%Y%m%d", errors="coerce"
        )
        # Open reservation = required - withdrawn
        bdmng = pd.to_numeric(_safe_col(resb_df, "BDMNG", 0), errors="coerce").fillna(0)
        enmng = pd.to_numeric(_safe_col(resb_df, "ENMNG", 0), errors="coerce").fillna(0)
        result["reserved_quantity"] = (bdmng - enmng).clip(lower=0)
        result["reservation_type"] = "PRODUCTION"  # RESB reservations are for production orders
        result["reference_id"] = _safe_col(resb_df, "AUFNR", "").astype(str).str.strip()

        # Filter to open reservations only
        result = result[result["reserved_quantity"] > 0]

        logger.info(f"Mapped {len(result)} reservation records")
        return result

    def map_shipment_lots(
        self,
        mch1_df: pd.DataFrame,
        mcha_df: pd.DataFrame = None,
        lips_df: pd.DataFrame = None,
    ) -> pd.DataFrame:
        """
        Map batch master (MCH1/MCHA) + delivery items (LIPS) to ShipmentLot.

        MCH1: Batch master (MATNR, CHARG, creation date)
        MCHA: Batch plant assignment (shelf life dates, country of origin)
        LIPS.CHARG: Batch assignment to delivery → links lot to shipment
        """
        logger.info("Mapping MCH1/MCHA/LIPS to ShipmentLot")

        if mch1_df.empty:
            return pd.DataFrame()

        batch = mch1_df.copy()
        batch["MATNR"] = batch["MATNR"].astype(str).str.strip()
        batch["CHARG"] = batch["CHARG"].astype(str).str.strip()

        # Enrich with plant-level shelf life from MCHA
        if mcha_df is not None and not mcha_df.empty:
            mcha = mcha_df.copy()
            mcha["MATNR"] = mcha["MATNR"].astype(str).str.strip()
            mcha["CHARG"] = mcha["CHARG"].astype(str).str.strip()
            merge_cols = ["MATNR", "CHARG"]
            extra = []
            for c in ["WERKS", "HSDAT", "VFDAT", "MAXLZ_MCHA", "LIESSION"]:
                if c in mcha.columns:
                    extra.append(c)
            batch = batch.merge(
                mcha[merge_cols + extra].drop_duplicates(subset=merge_cols, keep="first"),
                on=merge_cols,
                how="left",
            )

        # Link to shipments via LIPS.CHARG
        if lips_df is not None and not lips_df.empty and "CHARG" in lips_df.columns:
            lips_batch = lips_df[lips_df["CHARG"].astype(str).str.strip() != ""].copy()
            lips_batch["MATNR"] = lips_batch["MATNR"].astype(str).str.strip()
            lips_batch["CHARG"] = lips_batch["CHARG"].astype(str).str.strip()
            lips_batch["VBELN"] = lips_batch["VBELN"].astype(str).str.strip()
            lips_batch["_qty"] = pd.to_numeric(_safe_col(lips_batch, "LFIMG", 0), errors="coerce").fillna(0)
            # One lot record per shipment-batch combination
            lot_links = lips_batch[["VBELN", "MATNR", "CHARG", "WERKS", "_qty"]].drop_duplicates()
            lot_links = lot_links.merge(batch, on=["MATNR", "CHARG"], how="left", suffixes=("", "_batch"))
            result = pd.DataFrame()
            result["shipment_id"] = lot_links["VBELN"]
            result["product_id"] = lot_links["MATNR"]
            result["lot_number"] = lot_links["CHARG"]
            result["batch_id"] = lot_links["CHARG"]
            result["quantity"] = lot_links["_qty"]
            result["uom"] = "EA"
            result["manufacture_date"] = pd.to_datetime(
                _safe_col(lot_links, "HSDAT", None), errors="coerce"
            )
            result["expiration_date"] = pd.to_datetime(
                _safe_col(lot_links, "VFDAT", None), errors="coerce"
            )
            shelf_life = pd.to_numeric(_safe_col(lot_links, "MAXLZ_MCHA", 0), errors="coerce")
            result["shelf_life_days"] = shelf_life.fillna(0).astype(int)
            result["quality_status"] = "RELEASED"
            result["origin_site_id"] = _safe_col(lot_links, "WERKS", "").astype(str).str.strip()
            result["country_of_origin"] = ""
            result["source"] = "SAP_MCH1_LIPS"
        else:
            # Batch master without shipment link — create reference records
            result = pd.DataFrame()
            result["shipment_id"] = ""
            result["product_id"] = batch["MATNR"]
            result["lot_number"] = batch["CHARG"]
            result["batch_id"] = batch["CHARG"]
            result["quantity"] = 0.0
            result["uom"] = "EA"
            result["manufacture_date"] = pd.to_datetime(
                _safe_col(batch, "HSDAT", _safe_col(batch, "ERDAT", None)), errors="coerce"
            )
            result["expiration_date"] = pd.to_datetime(
                _safe_col(batch, "VFDAT", None), errors="coerce"
            )
            result["shelf_life_days"] = pd.to_numeric(
                _safe_col(batch, "MAXLZ_MCHA", 0), errors="coerce"
            ).fillna(0).astype(int)
            result["quality_status"] = "RELEASED"
            result["origin_site_id"] = _safe_col(batch, "WERKS", "").astype(str).str.strip()
            result["country_of_origin"] = ""
            result["source"] = "SAP_MCH1"

        logger.info(f"Mapped {len(result)} shipment lot records")
        return result

    def map_outbound_shipments(
        self,
        likp_df: pd.DataFrame,
        lips_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Map SAP deliveries (LIKP/LIPS) to OutboundShipment.

        OutboundShipment links a sales order line to a shipment with status tracking.
        LIPS.VGBEL/VGPOS references the originating sales order.
        """
        logger.info("Mapping LIKP/LIPS to OutboundShipment")

        if lips_df.empty:
            return pd.DataFrame()

        # Merge delivery header for dates/status
        header_cols = ["VBELN"]
        for col in ["KUNNR", "WADAT_IST", "LFDAT", "LDDAT", "BOLNR", "LIFNR"]:
            if col in likp_df.columns:
                header_cols.append(col)
        merged = lips_df.merge(likp_df[header_cols], on="VBELN", how="left")

        result = pd.DataFrame()
        result["order_id"] = _safe_col(merged, "VGBEL", "").astype(str).str.strip()
        result["order_line_number"] = pd.to_numeric(
            _safe_col(merged, "VGPOS", 0), errors="coerce"
        ).fillna(0).astype(int)
        result["shipment_id"] = merged["VBELN"].astype(str).str.strip()
        result["product_id"] = merged["MATNR"].astype(str).str.strip()
        result["site_id"] = merged["WERKS"].astype(str).str.strip()
        result["customer_site_id"] = _safe_col(merged, "KUNNR", "").astype(str).str.strip()
        result["shipped_quantity"] = pd.to_numeric(
            _safe_col(merged, "LFIMG", 0), errors="coerce"
        ).fillna(0)
        result["uom"] = _safe_col(merged, "MEINS", "EA").astype(str).str.strip()
        result["ship_date"] = pd.to_datetime(
            _safe_col(merged, "WADAT_IST", None), errors="coerce"
        )
        result["expected_delivery_date"] = pd.to_datetime(
            _safe_col(merged, "LFDAT", None), errors="coerce"
        )
        result["actual_delivery_date"] = pd.to_datetime(
            _safe_col(merged, "LDDAT", None), errors="coerce"
        )
        # Status
        has_actual = result["actual_delivery_date"].notna()
        has_ship = result["ship_date"].notna()
        result["status"] = "CREATED"
        result.loc[has_ship, "status"] = "SHIPPED"
        result.loc[has_actual, "status"] = "DELIVERED"
        result["carrier_id"] = _safe_col(merged, "LIFNR", "").astype(str).str.strip()
        result["tracking_number"] = _safe_col(merged, "BOLNR", "").astype(str).str.strip()
        result["source"] = "SAP_LIKP_LIPS"

        # Filter to lines that reference a sales order
        result = result[result["order_id"].str.len() > 0]

        logger.info(f"Mapped {len(result)} outbound shipment records")
        return result

    def map_final_assembly_schedule(
        self,
        afko_df: pd.DataFrame,
        afpo_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Map SAP production orders (AFKO/AFPO) to FinalAssemblySchedule.

        FAS applies to configure-to-order (CTO) and assemble-to-order (ATO) items.
        AFKO: Production order headers (dates, routing reference)
        AFPO: Production order items (material, plant, quantities)
        """
        logger.info("Mapping AFKO/AFPO to FinalAssemblySchedule")

        if afpo_df.empty:
            return pd.DataFrame()

        # Merge headers
        if not afko_df.empty:
            header_cols = ["AUFNR"]
            for c in ["GSTRP", "GLTRP", "PLNNR", "PLNAL", "GAMNG", "GMEIN"]:
                if c in afko_df.columns:
                    header_cols.append(c)
            merged = afpo_df.merge(afko_df[header_cols], on="AUFNR", how="left")
        else:
            merged = afpo_df.copy()

        result = pd.DataFrame()
        result["fas_id"] = "FAS-" + merged["AUFNR"].astype(str).str.strip()
        # Order reference from production order → sales order link (AFPO.KDAUF if available)
        result["order_id"] = _safe_col(merged, "KDAUF", "").astype(str).str.strip() if "KDAUF" in merged.columns else ""
        result["order_line_id"] = _safe_col(merged, "KDPOS", "").astype(str).str.strip() if "KDPOS" in merged.columns else ""
        result["product_id"] = merged["MATNR"].astype(str).str.strip()
        result["base_product_id"] = merged["MATNR"].astype(str).str.strip()
        result["site_id"] = _safe_col(merged, "PWERK", _safe_col(merged, "WERKS", "")).astype(str).str.strip()
        result["assembly_quantity"] = pd.to_numeric(
            _safe_col(merged, "PSMNG", _safe_col(merged, "GAMNG", 0)), errors="coerce"
        ).fillna(0)
        result["assembly_start_date"] = pd.to_datetime(
            _safe_col(merged, "GSTRP", None), errors="coerce"
        )
        result["assembly_end_date"] = pd.to_datetime(
            _safe_col(merged, "GLTRP", None), errors="coerce"
        )
        # Calculate assembly lead time
        start = result["assembly_start_date"]
        end = result["assembly_end_date"]
        result["assembly_lead_time_days"] = (end - start).dt.days.fillna(0).astype(int)

        # Status from AFPO.DESSION or simplified
        stat = _safe_col(merged, "DESSION", "").astype(str).str.strip()
        status_map = {"": "PLANNED", "REL": "RELEASED", "TECO": "COMPLETED", "CNF": "CONFIRMED"}
        result["status"] = stat.map(lambda x: status_map.get(x[:4], "PLANNED") if x else "PLANNED")

        result["work_center_id"] = ""
        result["production_process_id"] = _safe_col(merged, "PLNNR", "").astype(str).str.strip()
        result["priority"] = 3
        result["source"] = "SAP_AFKO_AFPO"

        logger.info(f"Mapped {len(result)} final assembly schedule records")
        return result

    def map_sourcing_schedule(self, eord_df: pd.DataFrame) -> pd.DataFrame:
        """
        Map source list (EORD) to SourcingSchedule.

        EORD defines approved vendor-plant assignments with validity periods
        which map to sourcing schedule time windows.
        """
        logger.info("Mapping EORD to SourcingSchedule")

        if eord_df.empty:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["id"] = (
            eord_df["MATNR"].astype(str).str.strip() + "-" +
            eord_df["WERKS"].astype(str).str.strip() + "-" +
            _safe_col(eord_df, "ZEESSION", "01").astype(str).str.strip()
        )
        result["description"] = (
            "Source " + eord_df["LIFNR"].astype(str).str.strip() +
            " → " + eord_df["WERKS"].astype(str).str.strip()
        )
        result["to_site_id"] = eord_df["WERKS"].astype(str).str.strip()
        result["tpartner_id"] = eord_df["LIFNR"].astype(str).str.strip()
        result["from_site_id"] = ""  # Vendor site not in EORD
        result["schedule_type"] = "custom"

        # NOTKZ: 1=normal, 2=blocked
        notkz = _safe_col(eord_df, "NOTKZ", "1").astype(str).str.strip()
        result["is_active"] = notkz != "2"

        result["eff_start_date"] = pd.to_datetime(
            _safe_col(eord_df, "VDATU", None), format="%Y%m%d", errors="coerce"
        )
        result["eff_end_date"] = pd.to_datetime(
            _safe_col(eord_df, "BDATU", None), format="%Y%m%d", errors="coerce"
        )

        result = result[result["is_active"]]
        result["source"] = "SAP_EORD"

        logger.info(f"Mapped {len(result)} sourcing schedule records")
        return result

    # ------------------------------------------------------------------
    # Operational Statistics → Distribution Parameters
    # ------------------------------------------------------------------

    def map_operational_stats_to_distributions(
        self,
        stats: Dict[str, List[Dict]],
    ) -> Dict[str, pd.DataFrame]:
        """Convert aggregated SAP operational statistics to distribution parameters.

        Takes the output of ``extract_operational_stats()`` (metric_key → list of
        stat dicts with min/p05/p25/median/p75/p95/max/mean/stddev/cnt) and fits
        the best distribution family per metric group.

        Returns a dict keyed by target entity (e.g. ``vendor_lead_time``,
        ``production_process``, ``transportation_lane``) with DataFrames ready
        for upsert.  Each row contains the business key columns plus a
        ``*_dist`` JSON column value.

        Distribution selection heuristic (no raw data, only summary stats):
        - Positive, right-skewed → lognormal (lead times, cycle times)
        - Bounded 0-1 → beta (yields, on-time rates)
        - Positive with known lower bound → weibull / gamma
        - Roughly symmetric → normal
        """
        result: Dict[str, pd.DataFrame] = {}

        # --- Supplier lead time → vendor_lead_time.lead_time_dist ----------
        if "supplier_lead_time" in stats and stats["supplier_lead_time"]:
            rows = []
            for r in stats["supplier_lead_time"]:
                dist = self._fit_positive_skewed(r)
                rows.append({
                    "tpartner_id": str(r.get("vendor_id", "")).strip(),
                    "product_id": str(r.get("material", "")).strip(),
                    "site_id": str(r.get("plant", "")).strip(),
                    "lead_time_days": r.get("mean"),
                    "lead_time_variability_days": r.get("stddev"),
                    "lead_time_dist": dist,
                    "source": "SAP_OPERATIONAL_STATS",
                })
            result["vendor_lead_time"] = pd.DataFrame(rows)

        # --- Supplier on-time → vendor_lead_time (on_time_rate_dist) -------
        if "supplier_on_time" in stats and stats["supplier_on_time"]:
            rows = []
            for r in stats["supplier_on_time"]:
                rate = r.get("on_time_rate")
                cnt = r.get("cnt", 0)
                dist = self._fit_rate(rate, cnt)
                rows.append({
                    "tpartner_id": str(r.get("vendor_id", "")).strip(),
                    "on_time_rate": rate,
                    "on_time_rate_dist": dist,
                    "source": "SAP_OPERATIONAL_STATS",
                })
            result["supplier_on_time"] = pd.DataFrame(rows)

        # --- Manufacturing cycle time → production_process.operation_time_dist
        if "manufacturing_cycle_time" in stats and stats["manufacturing_cycle_time"]:
            rows = []
            for r in stats["manufacturing_cycle_time"]:
                dist = self._fit_positive_skewed(r)
                rows.append({
                    "site_id": str(r.get("plant", "")).strip(),
                    "product_id": str(r.get("material", "")).strip(),
                    "operation_time": r.get("mean"),
                    "operation_time_dist": dist,
                    "source": "SAP_OPERATIONAL_STATS",
                })
            result["production_process_cycle"] = pd.DataFrame(rows)

        # --- Manufacturing yield → production_process.yield_dist -----------
        if "manufacturing_yield" in stats and stats["manufacturing_yield"]:
            rows = []
            for r in stats["manufacturing_yield"]:
                dist = self._fit_rate(r.get("mean"), r.get("cnt", 0),
                                       stddev=r.get("stddev"))
                rows.append({
                    "site_id": str(r.get("plant", "")).strip(),
                    "product_id": str(r.get("material", "")).strip(),
                    "yield_percentage": r.get("mean"),
                    "yield_dist": dist,
                    "source": "SAP_OPERATIONAL_STATS",
                })
            result["production_process_yield"] = pd.DataFrame(rows)

        # --- Manufacturing setup time → production_process.setup_time_dist -
        if "manufacturing_setup_time" in stats and stats["manufacturing_setup_time"]:
            rows = []
            for r in stats["manufacturing_setup_time"]:
                dist = self._fit_positive_skewed(r)
                rows.append({
                    "site_id": str(r.get("plant", "")).strip(),
                    "product_id": str(r.get("material", "")).strip(),
                    "setup_time": r.get("mean"),
                    "setup_time_dist": dist,
                    "source": "SAP_OPERATIONAL_STATS",
                })
            result["production_process_setup"] = pd.DataFrame(rows)

        # --- Machine MTBF → production_process.mtbf_dist ------------------
        if "machine_mtbf" in stats and stats["machine_mtbf"]:
            rows = []
            for r in stats["machine_mtbf"]:
                dist = self._fit_positive_skewed(r)
                rows.append({
                    "site_id": str(r.get("plant", "")).strip(),
                    "equipment_id": str(r.get("equipment", "")).strip(),
                    "mtbf_days": r.get("mean"),
                    "mtbf_dist": dist,
                    "source": "SAP_OPERATIONAL_STATS",
                })
            result["machine_mtbf"] = pd.DataFrame(rows)

        # --- Machine MTTR → production_process.mttr_dist ------------------
        if "machine_mttr" in stats and stats["machine_mttr"]:
            rows = []
            for r in stats["machine_mttr"]:
                dist = self._fit_positive_skewed(r)
                rows.append({
                    "site_id": str(r.get("plant", "")).strip(),
                    "equipment_id": str(r.get("equipment", "")).strip(),
                    "mttr_hours": r.get("mean"),
                    "mttr_dist": dist,
                    "source": "SAP_OPERATIONAL_STATS",
                })
            result["machine_mttr"] = pd.DataFrame(rows)

        # --- Transportation lead time → transportation_lane.*_dist --------
        if "transportation_lead_time" in stats and stats["transportation_lead_time"]:
            rows = []
            for r in stats["transportation_lead_time"]:
                dist = self._fit_positive_skewed(r)
                rows.append({
                    "from_site_id": str(r.get("ship_from", "")).strip(),
                    "to_site_id": str(r.get("ship_to", "")).strip(),
                    "supply_lead_time_dist": dist,
                    "source": "SAP_OPERATIONAL_STATS",
                })
            result["transportation_lane"] = pd.DataFrame(rows)

        # --- Quality rejection rate → production_process quality ----------
        if "quality_rejection_rate" in stats and stats["quality_rejection_rate"]:
            rows = []
            for r in stats["quality_rejection_rate"]:
                dist = self._fit_rate(r.get("mean"), r.get("cnt", 0),
                                       stddev=r.get("stddev"))
                rows.append({
                    "site_id": str(r.get("plant", "")).strip(),
                    "product_id": str(r.get("material", "")).strip(),
                    "rejection_rate": r.get("mean"),
                    "rejection_rate_dist": dist,
                    "source": "SAP_OPERATIONAL_STATS",
                })
            result["quality_rejection"] = pd.DataFrame(rows)

        # --- Demand variability → stored per product-site for forecasting -
        if "demand_variability" in stats and stats["demand_variability"]:
            rows = []
            for r in stats["demand_variability"]:
                dist = self._fit_positive_skewed(r)
                rows.append({
                    "product_id": str(r.get("material", "")).strip(),
                    "site_id": str(r.get("plant", "")).strip(),
                    "weekly_demand_mean": r.get("mean"),
                    "weekly_demand_stddev": r.get("stddev"),
                    "demand_dist": dist,
                    "source": "SAP_OPERATIONAL_STATS",
                })
            result["demand_variability"] = pd.DataFrame(rows)

        # --- Order fulfillment time ---
        if "order_fulfillment_time" in stats and stats["order_fulfillment_time"]:
            rows = []
            for r in stats["order_fulfillment_time"]:
                dist = self._fit_positive_skewed(r)
                rows.append({
                    "product_id": str(r.get("material", "")).strip(),
                    "site_id": str(r.get("plant", "")).strip(),
                    "fulfillment_days_mean": r.get("mean"),
                    "fulfillment_dist": dist,
                    "source": "SAP_OPERATIONAL_STATS",
                })
            result["order_fulfillment"] = pd.DataFrame(rows)

        total = sum(len(df) for df in result.values())
        logger.info(
            f"Mapped operational stats → {len(result)} entity groups, "
            f"{total} total distribution records"
        )
        return result

    # --- Private distribution fitting helpers -----------------------------

    @staticmethod
    def _fit_positive_skewed(r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Fit a distribution to positive, potentially right-skewed data.

        Uses only summary statistics (mean, stddev, p05, p95, median).
        Selects lognormal if skew detected (median < mean), else normal.
        Falls back to triangular if insufficient stats.
        """
        mean = r.get("mean")
        stddev = r.get("stddev")
        p05 = r.get("p05")
        p95 = r.get("p95")
        median = r.get("median")
        cnt = r.get("cnt", 0)

        if mean is None or cnt < 5:
            return None

        # Not enough variability info → triangular from percentiles
        if stddev is None or stddev == 0:
            lo = p05 if p05 is not None else r.get("min", mean * 0.8)
            hi = p95 if p95 is not None else r.get("max", mean * 1.2)
            mode = median if median is not None else mean
            return {
                "type": "triangular",
                "min": round(float(lo), 4),
                "mode": round(float(mode), 4),
                "max": round(float(hi), 4),
            }

        cv = stddev / mean if mean > 0 else 0

        # Detect right skew: median < mean indicates lognormal
        is_skewed = (
            (median is not None and mean > 0 and median < mean * 0.95)
            or cv > 0.5
        )

        if is_skewed and mean > 0 and stddev > 0:
            # Lognormal: derive mu_log, sigma_log from mean & stddev
            variance = stddev ** 2
            mu_log = math.log(mean ** 2 / math.sqrt(variance + mean ** 2))
            sigma_log = math.sqrt(math.log(1 + variance / mean ** 2))
            dist: Dict[str, Any] = {
                "type": "lognormal",
                "mean_log": round(mu_log, 6),
                "stddev_log": round(sigma_log, 6),
                "mean": round(float(mean), 4),
                "stddev": round(float(stddev), 4),
            }
        else:
            dist = {
                "type": "normal",
                "mean": round(float(mean), 4),
                "stddev": round(float(stddev), 4),
            }

        # Add percentile bounds for truncation
        if p05 is not None:
            dist["min"] = round(float(p05), 4)
        if p95 is not None:
            dist["max"] = round(float(p95), 4)

        return dist

    @staticmethod
    def _fit_rate(
        rate: Optional[float],
        cnt: int = 0,
        stddev: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fit a Beta distribution to a rate (0-1 bounded) metric.

        Uses method-of-moments: given mean μ and variance σ², compute
        α = μ × ((μ(1-μ)/σ²) - 1), β = (1-μ) × ((μ(1-μ)/σ²) - 1).
        """
        if rate is None or cnt < 5:
            return None

        mu = float(rate)
        # Clamp to valid Beta range
        mu = max(0.001, min(0.999, mu))

        if stddev is not None and stddev > 0:
            var = float(stddev) ** 2
            # Ensure valid: variance must be < mu*(1-mu)
            max_var = mu * (1 - mu) - 0.0001
            var = min(var, max_var) if max_var > 0 else 0.001
            if var > 0:
                common = (mu * (1 - mu) / var) - 1
                if common > 0:
                    alpha = mu * common
                    beta_param = (1 - mu) * common
                    return {
                        "type": "beta",
                        "alpha": round(alpha, 4),
                        "beta": round(beta_param, 4),
                        "mean": round(mu, 4),
                    }

        # Fallback: use count to estimate concentration
        # Higher count → narrower distribution
        alpha = mu * min(cnt, 100)
        beta_param = (1 - mu) * min(cnt, 100)
        return {
            "type": "beta",
            "alpha": round(max(alpha, 1.0), 4),
            "beta": round(max(beta_param, 1.0), 4),
            "mean": round(mu, 4),
        }
