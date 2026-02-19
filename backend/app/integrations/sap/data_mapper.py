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
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


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
        sites["address"] = ""  # Would come from additional address table
        sites["city"] = ""
        sites["state"] = ""
        sites["country"] = ""
        sites["postal_code"] = ""
        sites["latitude"] = np.nan
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
        sites["site_type"] = locations_df.get("LOCTYPE", "WAREHOUSE").str.upper()
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

    def map_s4hana_materials_to_products(self, materials_df: pd.DataFrame) -> pd.DataFrame:
        """
        Map S/4HANA materials to Supply Chain Products.

        Args:
            materials_df: DataFrame from S4HANAConnector.extract_materials()

        Returns:
            DataFrame in AWS Products schema
        """
        logger.info("Mapping S/4HANA materials to AWS Products")

        products = pd.DataFrame()

        # Map fields
        products["product_id"] = materials_df["MATNR"]
        products["product_name"] = materials_df.get("MAKTX", materials_df["MATNR"])
        products["product_description"] = materials_df.get("MAKTX", "")
        products["product_category"] = materials_df.get("MATKL", "")
        products["unit_of_measure"] = materials_df.get("MEINS", "EA")
        products["weight"] = pd.to_numeric(materials_df.get("NTGEW", 0), errors="coerce")
        products["weight_unit"] = materials_df.get("GEWEI", "KG")
        products["volume"] = pd.to_numeric(materials_df.get("VOLUM", 0), errors="coerce")
        products["volume_unit"] = materials_df.get("VOLEH", "M3")
        products["is_active"] = ~materials_df.get("LVORM", "").astype(bool)

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
        inventory_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Map S/4HANA inventory (MARD) to AWS InventoryLevel.

        Args:
            inventory_df: DataFrame from S4HANAConnector.extract_inventory()

        Returns:
            DataFrame in AWS InventoryLevel schema
        """
        logger.info("Mapping S/4HANA inventory to AWS InventoryLevel")

        inv_levels = pd.DataFrame()

        inv_levels["site_id"] = inventory_df["WERKS"]
        inv_levels["product_id"] = inventory_df["MATNR"]
        inv_levels["inventory_date"] = datetime.now()
        inv_levels["available_quantity"] = pd.to_numeric(
            inventory_df.get("LABST", 0), errors="coerce"
        )
        inv_levels["in_transit_quantity"] = pd.to_numeric(
            inventory_df.get("UMLME", 0), errors="coerce"
        )
        inv_levels["reserved_quantity"] = pd.to_numeric(
            inventory_df.get("INSME", 0), errors="coerce"
        )
        inv_levels["safety_stock_quantity"] = 0.0  # Would come from MARC.EISBE
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
        supply_plan["source_type"] = supply_orders.get("ORDERTYPE", "").map({
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
        so_items: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Map S/4HANA sales orders (VBAK/VBAP) to AWS SalesOrder.

        Args:
            so_headers: VBAK header data
            so_items: VBAP item data

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

        sales_orders = pd.DataFrame()

        sales_orders["so_number"] = sos["VBELN"]
        sales_orders["so_line_number"] = sos["POSNR"]
        sales_orders["customer_id"] = sos["KUNNR"]
        sales_orders["product_id"] = sos["MATNR"]
        sales_orders["source_site_id"] = sos["WERKS"]
        sales_orders["order_date"] = pd.to_datetime(sos["ERDAT"], errors="coerce")
        sales_orders["requested_delivery_date"] = pd.NaT  # Would come from VBEP
        sales_orders["order_quantity"] = pd.to_numeric(sos["KWMENG"], errors="coerce")
        sales_orders["open_quantity"] = pd.to_numeric(sos["KWMENG"], errors="coerce")
        sales_orders["unit_of_measure"] = sos.get("VRKME", "EA")
        sales_orders["unit_price"] = pd.to_numeric(sos.get("NETPR", 0), errors="coerce")
        sales_orders["currency"] = sos.get("WAERK", "USD")
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
            delivery_headers: LIKP header data
            delivery_items: LIPS item data

        Returns:
            DataFrame in AWS Shipment schema
        """
        logger.info("Mapping S/4HANA deliveries to AWS Shipment")

        # Merge headers and items
        deliveries = delivery_items.merge(
            delivery_headers[["VBELN", "KUNNR", "LFDAT", "WADAT_IST"]],
            on="VBELN",
            how="left"
        )

        shipments = pd.DataFrame()

        shipments["shipment_id"] = deliveries["VBELN"]
        shipments["shipment_line_number"] = deliveries["POSNR"]
        shipments["product_id"] = deliveries["MATNR"]
        shipments["source_site_id"] = deliveries["WERKS"]
        shipments["destination_site_id"] = deliveries.get("KUNNR", "")
        shipments["shipment_date"] = pd.to_datetime(
            deliveries.get("WADAT_IST", deliveries["LFDAT"]), errors="coerce"
        )
        shipments["expected_delivery_date"] = pd.to_datetime(
            deliveries["LFDAT"], errors="coerce"
        )
        shipments["actual_delivery_date"] = pd.to_datetime(
            deliveries.get("WADAT_IST"), errors="coerce"
        )
        shipments["shipped_quantity"] = pd.to_numeric(
            deliveries.get("LFIMG", 0), errors="coerce"
        )
        shipments["unit_of_measure"] = deliveries.get("VRKME", "EA")
        shipments["shipment_type"] = "OUTBOUND"
        shipments["status"] = "SHIPPED"

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

        # SAP EISBE is absolute safety stock quantity
        inv_policy['ss_policy'] = 'abs_level'
        inv_policy['ss_quantity'] = pd.to_numeric(
            marc_df.get('EISBE', 0), errors='coerce'
        ).fillna(0)
        inv_policy['ss_days'] = 0  # Not used for abs_level

        # Lead time from PLIFZ (planned delivery time) or DZEIT (production time)
        plifz = pd.to_numeric(marc_df.get('PLIFZ', 0), errors='coerce').fillna(0)
        dzeit = pd.to_numeric(marc_df.get('DZEIT', 0), errors='coerce').fillna(0)
        inv_policy['lead_time_days'] = plifz.where(plifz > 0, dzeit).astype(int)

        # Review period - not directly in MARC, default to lead time
        inv_policy['review_period'] = inv_policy['lead_time_days']

        # MRP settings for reference
        inv_policy['mrp_controller'] = marc_df.get('DISPO', '').astype(str).str.strip()
        inv_policy['mrp_type'] = marc_df.get('DISMM', '').astype(str).str.strip()
        inv_policy['availability_check_group'] = marc_df.get('MTVFP', '').astype(str).str.strip()

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
