"""
SAP CSV Exporter

Generates SAP-formatted CSV files from platform data for deployment:
- Day 1: Full master data + current state → ZIP of 19 CSVs
- Day 2: Delta records designed to trigger CDC → disruption-flavored CSVs

Reverse mapping: AWS SC entities → SAP table format.
Compliant with existing CSVDataLoader import patterns (uppercase headers,
UTF-8 encoding, comma-delimited).

Usage:
    exporter = SAPCSVExporter(db, config_id)
    zip_path = await exporter.export_day1(output_dir)
    delta_path = await exporter.export_day2(output_dir, profile="demand_spike")
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)


@dataclass
class Day2ScenarioProfile:
    """Configuration for Day 2 delta generation."""
    name: str = "mixed"

    # Demand spike: increase qty for selected customers
    demand_spike_pct: float = 0.40  # +40%
    demand_spike_customers: int = 3  # Top 3 by volume

    # Lead time increase: delay for selected suppliers
    lead_time_increase_days: int = 5
    lead_time_affected_suppliers: int = 2

    # Rush orders: priority-1 orders
    rush_order_count: int = 3

    # Inventory shrink: reduce on-hand for selected products
    inventory_shrink_pct: float = 0.30  # -30%
    inventory_shrink_products: int = 5


class SAPCSVExporter:
    """
    Exports supply chain data as SAP-formatted CSV files.

    Supports all 19 standard SAP tables mapped from AWS SC entities.
    """

    def __init__(self, db: AsyncSession, config_id: int):
        self.db = db
        self.config_id = config_id
        self._topology = None

    async def export_day1(self, output_dir: Path) -> Path:
        """
        Export full master data + current state as ZIP of 19 SAP CSVs.

        Returns path to the generated ZIP file.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        await self._load_data()

        tables = {}

        # Master Data
        tables["MARA"] = self._export_mara()
        tables["MARC"] = self._export_marc()
        tables["T001W"] = self._export_t001w()
        tables["LFA1"] = self._export_lfa1()
        tables["KNA1"] = self._export_kna1()
        tables["STPO"] = self._export_stpo()

        # Inventory
        tables["MARD"] = self._export_mard()

        # Purchase Orders
        tables["EKKO"] = self._export_ekko()
        tables["EKPO"] = self._export_ekpo()

        # Sales Orders
        tables["VBAK"] = self._export_vbak()
        tables["VBAP"] = self._export_vbap()

        # Deliveries
        tables["LIKP"] = self._export_likp()
        tables["LIPS"] = self._export_lips()

        # Production Orders
        tables["AFKO"] = self._export_afko()
        tables["AFPO"] = self._export_afpo()

        # Schedule Lines
        tables["EKET"] = self._export_eket()

        # Reservations
        tables["RESB"] = self._export_resb()

        # APO tables
        tables["SAPAPO_LOC"] = self._export_sapapo_loc()
        tables["SAPAPO_SNPFC"] = self._export_sapapo_snpfc()

        # Write ZIP
        zip_name = f"sap_day1_{self.config_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
        zip_path = output_dir / zip_name

        with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED) as zf:
            for table_name, rows in tables.items():
                if not rows:
                    continue
                csv_content = self._rows_to_csv(rows)
                zf.writestr(f"{table_name}.csv", csv_content)
                logger.info(f"  {table_name}: {len(rows) - 1} records")  # -1 for header

        logger.info(f"Day 1 export complete: {zip_path} ({len(tables)} tables)")
        return zip_path

    async def export_day2(
        self,
        output_dir: Path,
        profile: Optional[Day2ScenarioProfile] = None,
        seed: int = 42,
    ) -> Path:
        """
        Export Day 2 delta CSVs designed to trigger CDC events.

        Returns path to the generated ZIP file.
        """
        if profile is None:
            profile = Day2ScenarioProfile()

        output_dir.mkdir(parents=True, exist_ok=True)
        await self._load_data()

        rng = np.random.RandomState(seed)
        tables = {}

        # Demand spike: new sales orders with elevated quantities
        if profile.demand_spike_pct > 0:
            vbak, vbap = self._generate_demand_spike(profile, rng)
            tables["VBAK"] = vbak
            tables["VBAP"] = vbap

        # Lead time increase: schedule lines with delayed dates
        if profile.lead_time_increase_days > 0:
            tables["EKET"] = self._generate_lead_time_delay(profile, rng)

        # Rush orders: priority-1 sales orders
        if profile.rush_order_count > 0:
            rush_vbak, rush_vbap = self._generate_rush_orders(profile, rng)
            # Merge with existing demand spike if present
            if "VBAK" in tables:
                tables["VBAK"].extend(rush_vbak[1:])  # Skip header
                tables["VBAP"].extend(rush_vbap[1:])
            else:
                tables["VBAK"] = rush_vbak
                tables["VBAP"] = rush_vbap

        # Inventory shrink: reduced LABST for selected products
        if profile.inventory_shrink_pct > 0:
            tables["MARD"] = self._generate_inventory_shrink(profile, rng)

        # Write ZIP
        zip_name = f"sap_day2_{self.config_id}_{profile.name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
        zip_path = output_dir / zip_name

        with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED) as zf:
            for table_name, rows in tables.items():
                if not rows:
                    continue
                csv_content = self._rows_to_csv(rows)
                zf.writestr(f"{table_name}.csv", csv_content)
                logger.info(f"  Day 2 {table_name}: {len(rows) - 1} delta records")

        logger.info(f"Day 2 export complete: {zip_path} (profile={profile.name})")
        return zip_path

    # ── Data Loading ──

    async def _load_data(self):
        """Load all relevant data for export."""
        if self._topology is not None:
            return

        from app.services.dag_simulator import load_topology
        self._topology = await load_topology(self.config_id, self.db)

        # Load additional entities
        from app.models.sc_entities import (
            InvLevel, Forecast, ProductBOM, TradingPartner,
            VendorProduct, VendorLeadTime, InboundOrderLine,
            OutboundOrderLine, Shipment,
        )

        # Inventory levels
        result = await self.db.execute(
            select(InvLevel).where(InvLevel.config_id == self.config_id)
        )
        self._inv_levels = list(result.scalars().all())

        # Forecasts
        result = await self.db.execute(
            select(Forecast).where(Forecast.config_id == self.config_id)
        )
        self._forecasts = list(result.scalars().all())

        # Product BOMs
        result = await self.db.execute(
            select(ProductBOM).where(ProductBOM.config_id == self.config_id)
        )
        self._boms = list(result.scalars().all())

        # Trading partners
        result = await self.db.execute(
            select(TradingPartner).where(TradingPartner.config_id == self.config_id)
        )
        self._trading_partners = list(result.scalars().all())

        # Vendor products
        result = await self.db.execute(
            select(VendorProduct).where(VendorProduct.config_id == self.config_id)
        )
        self._vendor_products = list(result.scalars().all())

        # Vendor lead times
        result = await self.db.execute(
            select(VendorLeadTime).where(VendorLeadTime.config_id == self.config_id)
        )
        self._vendor_lead_times = list(result.scalars().all())

        # Inbound orders
        try:
            result = await self.db.execute(
                select(InboundOrderLine).where(InboundOrderLine.config_id == self.config_id)
            )
            self._inbound_orders = list(result.scalars().all())
        except Exception:
            self._inbound_orders = []

        # Outbound orders
        try:
            result = await self.db.execute(
                select(OutboundOrderLine).where(OutboundOrderLine.config_id == self.config_id)
            )
            self._outbound_orders = list(result.scalars().all())
        except Exception:
            self._outbound_orders = []

        # Shipments
        try:
            result = await self.db.execute(
                select(Shipment).where(Shipment.config_id == self.config_id)
            )
            self._shipments = list(result.scalars().all())
        except Exception:
            self._shipments = []

    # ── Day 1 Table Exporters ──

    def _export_mara(self) -> List[List[str]]:
        """MARA - Material Master General Data."""
        rows = [["MATNR", "MAKTX", "MEINS", "MTART", "MATKL", "BRGEW", "GEWEI", "NTGEW"]]
        for p in self._topology.products:
            category = getattr(p, 'category', '') or ''
            mat_type = "FERT"  # Finished good
            if 'raw' in category.lower() or 'component' in category.lower():
                mat_type = "ROH"
            rows.append([
                str(p.id),
                getattr(p, 'description', '') or getattr(p, 'name', str(p.id)),
                getattr(p, 'base_uom', 'EA') or 'EA',
                mat_type,
                category[:18] if category else '',
                str(getattr(p, 'weight', '') or ''),
                'KG',
                str(getattr(p, 'weight', '') or ''),
            ])
        return rows

    def _export_marc(self) -> List[List[str]]:
        """MARC - Material Master Plant Data."""
        rows = [["MATNR", "WERKS", "MMSTA", "PLIFZ", "EISBE", "MINBE"]]
        # Cross-product of products × inventory sites
        for site in self._topology.inventory_sites:
            for p in self._topology.products:
                # Lead time from upstream
                lead_time = 0
                for up_name, lane in self._topology.upstream_map.get(site.name, []):
                    lt = getattr(lane, 'lead_time', None) or getattr(lane, 'transit_time', 5)
                    lead_time = max(lead_time, lt)

                # Safety stock from inv policies
                ss = 0.0
                policies = self._topology.inv_policies.get(site.name, {})
                p_policy = policies.get(str(p.id), {})
                ss = p_policy.get('ss_quantity', 0) or 0

                rows.append([
                    str(p.id),
                    site.name,
                    '',  # MMSTA - status
                    str(lead_time),
                    str(int(ss)),
                    str(int(ss * 0.5)),  # Min stock ~ 50% of safety stock
                ])
        return rows

    def _export_mard(self) -> List[List[str]]:
        """MARD - Inventory by Storage Location."""
        rows = [["MATNR", "WERKS", "LGORT", "LABST", "UMLME", "INSME"]]

        if self._inv_levels:
            for inv in self._inv_levels:
                rows.append([
                    str(inv.product_id),
                    str(inv.site_id),
                    '0001',  # Default storage location
                    str(int(getattr(inv, 'on_hand_qty', 0) or 0)),
                    str(int(getattr(inv, 'in_transit_qty', 0) or 0)),
                    str(int(getattr(inv, 'allocated_qty', 0) or 0)),
                ])
        else:
            # Generate from initial inventory
            for site_name, products in self._topology.initial_inventory.items():
                for prod_id, qty in products.items():
                    rows.append([
                        str(prod_id),
                        site_name,
                        '0001',
                        str(int(qty)),
                        '0',
                        '0',
                    ])
        return rows

    def _export_t001w(self) -> List[List[str]]:
        """T001W - Plants/Branches."""
        rows = [["WERKS", "NAME1", "ORT01", "REGIO", "LAND1"]]
        for site in self._topology.sites:
            attrs = getattr(site, 'attributes', {}) or {}
            geo = attrs.get('geo', {})
            rows.append([
                site.name,
                getattr(site, 'description', '') or site.name,
                geo.get('city', ''),
                geo.get('state', ''),
                geo.get('country', 'US'),
            ])
        return rows

    def _export_lfa1(self) -> List[List[str]]:
        """LFA1 - Vendor Master."""
        rows = [["LIFNR", "NAME1", "ORT01", "REGIO", "LAND1"]]

        if self._trading_partners:
            for tp in self._trading_partners:
                tp_type = getattr(tp, 'tpartner_type', '') or ''
                if 'vendor' in tp_type.lower() or 'supplier' in tp_type.lower():
                    rows.append([
                        str(tp.id),
                        getattr(tp, 'description', '') or str(tp.id),
                        getattr(tp, 'city', '') or '',
                        getattr(tp, 'state_prov', '') or '',
                        getattr(tp, 'country', 'US') or 'US',
                    ])
        else:
            # Fall back to supply sites
            for site in self._topology.supply_sites:
                attrs = getattr(site, 'attributes', {}) or {}
                geo = attrs.get('geo', {})
                rows.append([
                    site.name,
                    getattr(site, 'description', '') or site.name,
                    geo.get('city', ''),
                    geo.get('state', ''),
                    geo.get('country', 'US'),
                ])
        return rows

    def _export_kna1(self) -> List[List[str]]:
        """KNA1 - Customer Master."""
        rows = [["KUNNR", "NAME1", "ORT01", "REGIO", "LAND1"]]

        if self._trading_partners:
            for tp in self._trading_partners:
                tp_type = getattr(tp, 'tpartner_type', '') or ''
                if 'customer' in tp_type.lower():
                    rows.append([
                        str(tp.id),
                        getattr(tp, 'description', '') or str(tp.id),
                        getattr(tp, 'city', '') or '',
                        getattr(tp, 'state_prov', '') or '',
                        getattr(tp, 'country', 'US') or 'US',
                    ])
        else:
            for site in self._topology.demand_sites:
                attrs = getattr(site, 'attributes', {}) or {}
                geo = attrs.get('geo', {})
                rows.append([
                    site.name,
                    getattr(site, 'description', '') or site.name,
                    geo.get('city', ''),
                    geo.get('state', ''),
                    geo.get('country', 'US'),
                ])
        return rows

    def _export_stpo(self) -> List[List[str]]:
        """STPO - Bill of Materials Items."""
        rows = [["STLNR", "IDNRK", "MENGE", "MEINS"]]
        for bom in self._boms:
            rows.append([
                str(getattr(bom, 'parent_product_id', '')),
                str(getattr(bom, 'component_product_id', '')),
                str(getattr(bom, 'quantity_per', 1.0)),
                getattr(bom, 'uom', 'EA') or 'EA',
            ])
        return rows

    def _export_ekko(self) -> List[List[str]]:
        """EKKO - Purchase Order Headers."""
        rows = [["EBELN", "BUKRS", "BSTYP", "LIFNR", "BEDAT"]]
        today = datetime.utcnow().strftime('%Y%m%d')

        if self._inbound_orders:
            # Unique PO headers from inbound order lines
            seen_orders = set()
            for order in self._inbound_orders:
                order_id = getattr(order, 'order_id', None) or str(order.id)
                if order_id in seen_orders:
                    continue
                seen_orders.add(order_id)
                rows.append([
                    order_id,
                    '1000',  # Company code
                    'NB',    # Standard PO
                    str(getattr(order, 'supplier_id', '') or ''),
                    getattr(order, 'order_date', today) or today,
                ])
        else:
            # Generate synthetic POs from supplier lanes
            po_num = 4500000001
            for site in self._topology.supply_sites:
                rows.append([
                    str(po_num),
                    '1000',
                    'NB',
                    site.name,
                    today,
                ])
                po_num += 1
        return rows

    def _export_ekpo(self) -> List[List[str]]:
        """EKPO - Purchase Order Items."""
        rows = [["EBELN", "EBELP", "MATNR", "WERKS", "MENGE", "NETPR"]]

        if self._inbound_orders:
            for order in self._inbound_orders:
                order_id = getattr(order, 'order_id', None) or str(order.id)
                rows.append([
                    order_id,
                    str(getattr(order, 'line_number', '00010') or '00010'),
                    str(getattr(order, 'product_id', '')),
                    str(getattr(order, 'site_id', '')),
                    str(getattr(order, 'ordered_quantity', 0) or 0),
                    str(getattr(order, 'unit_price', 0) or 0),
                ])
        else:
            # Generate synthetic PO lines
            po_num = 4500000001
            dc_name = self._topology.inventory_sites[0].name if self._topology.inventory_sites else 'DC'
            for site in self._topology.supply_sites:
                line = 10
                for p in self._topology.products[:3]:  # 3 products per supplier
                    rows.append([
                        str(po_num),
                        str(line).zfill(5),
                        str(p.id),
                        dc_name,
                        str(100),
                        str(getattr(p, 'unit_cost', 10.0) or 10.0),
                    ])
                    line += 10
                po_num += 1
        return rows

    def _export_vbak(self) -> List[List[str]]:
        """VBAK - Sales Order Headers."""
        rows = [["VBELN", "AUART", "KUNNR", "ERDAT", "VKORG"]]
        today = datetime.utcnow().strftime('%Y%m%d')

        if self._outbound_orders:
            seen_orders = set()
            for order in self._outbound_orders:
                order_id = getattr(order, 'order_id', None) or str(order.id)
                if order_id in seen_orders:
                    continue
                seen_orders.add(order_id)
                customer = getattr(order, 'customer_id', '') or ''
                rows.append([
                    order_id,
                    'TA',  # Standard order
                    str(customer),
                    getattr(order, 'order_date', today) or today,
                    '1000',
                ])
        else:
            # Generate synthetic SOs from customer sites
            so_num = 5000000001
            for site in self._topology.demand_sites:
                rows.append([
                    str(so_num),
                    'TA',
                    site.name,
                    today,
                    '1000',
                ])
                so_num += 1
        return rows

    def _export_vbap(self) -> List[List[str]]:
        """VBAP - Sales Order Items."""
        rows = [["VBELN", "POSNR", "MATNR", "KWMENG", "NETPR"]]

        if self._outbound_orders:
            for order in self._outbound_orders:
                order_id = getattr(order, 'order_id', None) or str(order.id)
                rows.append([
                    order_id,
                    str(getattr(order, 'line_number', '000010') or '000010'),
                    str(getattr(order, 'product_id', '')),
                    str(getattr(order, 'ordered_quantity', 0) or 0),
                    str(getattr(order, 'unit_price', 0) or 0),
                ])
        else:
            so_num = 5000000001
            for site in self._topology.demand_sites:
                line = 10
                # Each customer orders ~5 products
                for p in self._topology.products[:5]:
                    # Use forecast as basis for order qty
                    forecasts = self._topology.forecasts.get(site.name, {})
                    p_fcst = forecasts.get(str(p.id), [])
                    qty = int(p_fcst[0]) if p_fcst else 50
                    rows.append([
                        str(so_num),
                        str(line).zfill(6),
                        str(p.id),
                        str(qty),
                        str(getattr(p, 'unit_price', 20.0) or 20.0),
                    ])
                    line += 10
                so_num += 1
        return rows

    def _export_likp(self) -> List[List[str]]:
        """LIKP - Delivery Headers."""
        rows = [["VBELN", "WADAT_IST", "LFART", "KUNNR"]]
        today = datetime.utcnow().strftime('%Y%m%d')

        if self._shipments:
            seen = set()
            for s in self._shipments:
                ship_id = str(s.id)
                if ship_id in seen:
                    continue
                seen.add(ship_id)
                rows.append([
                    ship_id,
                    str(getattr(s, 'ship_date', today) or today),
                    'LF',  # Standard delivery
                    str(getattr(s, 'to_site_id', '') or ''),
                ])
        else:
            # Generate a few sample deliveries
            dn_num = 8000000001
            for site in self._topology.demand_sites[:5]:
                rows.append([
                    str(dn_num),
                    today,
                    'LF',
                    site.name,
                ])
                dn_num += 1
        return rows

    def _export_lips(self) -> List[List[str]]:
        """LIPS - Delivery Items."""
        rows = [["VBELN", "POSNR", "MATNR", "LFIMG"]]

        if self._shipments:
            for s in self._shipments:
                rows.append([
                    str(s.id),
                    '000010',
                    str(getattr(s, 'product_id', '') or ''),
                    str(getattr(s, 'quantity', 0) or 0),
                ])
        else:
            dn_num = 8000000001
            for site in self._topology.demand_sites[:5]:
                line = 10
                for p in self._topology.products[:3]:
                    rows.append([
                        str(dn_num),
                        str(line).zfill(6),
                        str(p.id),
                        '50',
                    ])
                    line += 10
                dn_num += 1
        return rows

    def _export_afko(self) -> List[List[str]]:
        """AFKO - Production Order Headers."""
        rows = [["AUFNR", "PLNBEZ", "GSTRP", "GLTRP"]]
        today = datetime.utcnow().strftime('%Y%m%d')
        next_week = (datetime.utcnow() + timedelta(days=7)).strftime('%Y%m%d')

        # Generate production orders for manufacturer sites
        mo_num = 1000001
        for site in self._topology.sites:
            master_type = getattr(site, 'master_type', '')
            if str(master_type).upper() == 'MANUFACTURER':
                for p in self._topology.products[:3]:
                    rows.append([
                        str(mo_num),
                        str(p.id),
                        today,
                        next_week,
                    ])
                    mo_num += 1
        return rows

    def _export_afpo(self) -> List[List[str]]:
        """AFPO - Production Order Items."""
        rows = [["AUFNR", "POSNR", "MATNR", "PSMNG"]]
        mo_num = 1000001
        for site in self._topology.sites:
            master_type = getattr(site, 'master_type', '')
            if str(master_type).upper() == 'MANUFACTURER':
                for p in self._topology.products[:3]:
                    rows.append([
                        str(mo_num),
                        '0001',
                        str(p.id),
                        '100',
                    ])
                    mo_num += 1
        return rows

    def _export_eket(self) -> List[List[str]]:
        """EKET - PO Schedule Lines."""
        rows = [["EBELN", "EBELP", "ETENR", "EINDT", "MENGE"]]
        today = datetime.utcnow()

        if self._inbound_orders:
            for order in self._inbound_orders:
                order_id = getattr(order, 'order_id', None) or str(order.id)
                line = getattr(order, 'line_number', '00010') or '00010'
                qty = getattr(order, 'ordered_quantity', 100) or 100
                delivery_date = today + timedelta(days=7)
                rows.append([
                    order_id,
                    str(line),
                    '0001',
                    delivery_date.strftime('%Y%m%d'),
                    str(int(qty)),
                ])
        else:
            po_num = 4500000001
            for site in self._topology.supply_sites:
                # Lead time from topology
                lt = 7
                for vlt_name, vlt_days in self._topology.vendor_lead_times.get(site.name, {}).items():
                    lt = max(lt, vlt_days)

                delivery_date = today + timedelta(days=lt)
                line = 10
                for p in self._topology.products[:3]:
                    rows.append([
                        str(po_num),
                        str(line).zfill(5),
                        '0001',
                        delivery_date.strftime('%Y%m%d'),
                        '100',
                    ])
                    line += 10
                po_num += 1
        return rows

    def _export_resb(self) -> List[List[str]]:
        """RESB - Reservations/Allocations."""
        rows = [["RSNUM", "RSPOS", "MATNR", "WERKS", "BDMNG"]]

        # Generate from allocations if available
        from app.models.powell_allocation import PowellAllocation
        try:
            from sqlalchemy import select as sel
            # This is async, but _export methods are sync so we skip DB
            # and generate synthetic reservation data
            pass
        except Exception:
            pass

        # Generate synthetic reservations
        res_num = 1
        dc_name = self._topology.inventory_sites[0].name if self._topology.inventory_sites else 'DC'
        for p in self._topology.products[:10]:
            rows.append([
                str(res_num).zfill(10),
                '0001',
                str(p.id),
                dc_name,
                '50',
            ])
            res_num += 1
        return rows

    def _export_sapapo_loc(self) -> List[List[str]]:
        """/SAPAPO/LOC - APO Locations."""
        rows = [["LOCNO", "LOCTYPE", "NAME"]]
        for site in self._topology.sites:
            master_type = getattr(site, 'master_type', 'INVENTORY')
            loc_type = '1001'  # Plant
            if str(master_type).upper() == 'MARKET_SUPPLY':
                loc_type = '1002'  # Vendor
            elif str(master_type).upper() == 'MARKET_DEMAND':
                loc_type = '1010'  # Customer
            rows.append([
                site.name,
                loc_type,
                getattr(site, 'description', '') or site.name,
            ])
        return rows

    def _export_sapapo_snpfc(self) -> List[List[str]]:
        """/SAPAPO/SNPFC - APO Forecast."""
        rows = [["MATNR", "LOCNO", "PERIODID", "QUANTITY"]]

        for site_name, products in self._topology.forecasts.items():
            for prod_id, weekly_fcst in products.items():
                for week_idx, qty in enumerate(weekly_fcst[:52]):
                    base_date = datetime.utcnow() + timedelta(weeks=week_idx)
                    period_id = base_date.strftime('%Y%m%d')
                    rows.append([
                        str(prod_id),
                        site_name,
                        period_id,
                        str(int(qty)),
                    ])
        return rows

    # ── Day 2 Delta Generators ──

    def _generate_demand_spike(
        self, profile: Day2ScenarioProfile, rng: np.random.RandomState
    ) -> tuple:
        """Generate elevated demand VBAK/VBAP records."""
        today = datetime.utcnow().strftime('%Y%m%d')
        vbak = [["VBELN", "AUART", "KUNNR", "ERDAT", "VKORG"]]
        vbap = [["VBELN", "POSNR", "MATNR", "KWMENG", "NETPR"]]

        # Pick top customers
        customers = self._topology.demand_sites[:profile.demand_spike_customers]
        so_num = 9000000001

        for customer in customers:
            vbak.append([
                str(so_num),
                'TA',
                customer.name,
                today,
                '1000',
            ])

            line = 10
            for p in self._topology.products:
                forecasts = self._topology.forecasts.get(customer.name, {})
                p_fcst = forecasts.get(str(p.id), [])
                base_qty = int(p_fcst[0]) if p_fcst else 50

                # Spike by profile percentage
                spiked_qty = int(base_qty * (1 + profile.demand_spike_pct))

                vbap.append([
                    str(so_num),
                    str(line).zfill(6),
                    str(p.id),
                    str(spiked_qty),
                    str(getattr(p, 'unit_price', 20.0) or 20.0),
                ])
                line += 10

            so_num += 1

        return vbak, vbap

    def _generate_lead_time_delay(
        self, profile: Day2ScenarioProfile, rng: np.random.RandomState
    ) -> List[List[str]]:
        """Generate EKET records with delayed delivery dates."""
        rows = [["EBELN", "EBELP", "ETENR", "EINDT", "MENGE"]]
        today = datetime.utcnow()

        # Pick affected suppliers
        suppliers = self._topology.supply_sites[:profile.lead_time_affected_suppliers]
        po_num = 9500000001

        for supplier in suppliers:
            lt_base = 7
            for vlt_name, vlt_days in self._topology.vendor_lead_times.get(supplier.name, {}).items():
                lt_base = max(lt_base, vlt_days)

            delayed_lt = lt_base + profile.lead_time_increase_days
            delivery_date = today + timedelta(days=delayed_lt)

            line = 10
            for p in self._topology.products[:5]:
                rows.append([
                    str(po_num),
                    str(line).zfill(5),
                    '0001',
                    delivery_date.strftime('%Y%m%d'),
                    '100',
                ])
                line += 10
            po_num += 1

        return rows

    def _generate_rush_orders(
        self, profile: Day2ScenarioProfile, rng: np.random.RandomState
    ) -> tuple:
        """Generate priority-1 rush order VBAK/VBAP records."""
        today = datetime.utcnow().strftime('%Y%m%d')
        vbak = [["VBELN", "AUART", "KUNNR", "ERDAT", "VKORG"]]
        vbap = [["VBELN", "POSNR", "MATNR", "KWMENG", "NETPR"]]

        # Pick random customers for rush orders
        customer_indices = rng.choice(
            len(self._topology.demand_sites),
            size=min(profile.rush_order_count, len(self._topology.demand_sites)),
            replace=False,
        )

        so_num = 9800000001
        for idx in customer_indices:
            customer = self._topology.demand_sites[idx]
            vbak.append([
                str(so_num),
                'SO',  # Rush/special order type
                customer.name,
                today,
                '1000',
            ])

            # Rush orders for 2-3 products with larger quantities
            products = rng.choice(
                self._topology.products,
                size=min(3, len(self._topology.products)),
                replace=False,
            )
            line = 10
            for p in products:
                qty = rng.randint(100, 300)
                vbap.append([
                    str(so_num),
                    str(line).zfill(6),
                    str(p.id),
                    str(qty),
                    str(getattr(p, 'unit_price', 20.0) or 20.0),
                ])
                line += 10
            so_num += 1

        return vbak, vbap

    def _generate_inventory_shrink(
        self, profile: Day2ScenarioProfile, rng: np.random.RandomState
    ) -> List[List[str]]:
        """Generate MARD records with reduced LABST."""
        rows = [["MATNR", "WERKS", "LGORT", "LABST", "UMLME", "INSME"]]

        # Pick affected products
        product_indices = rng.choice(
            len(self._topology.products),
            size=min(profile.inventory_shrink_products, len(self._topology.products)),
            replace=False,
        )

        dc_name = self._topology.inventory_sites[0].name if self._topology.inventory_sites else 'DC'

        for idx in product_indices:
            p = self._topology.products[idx]

            # Get current inventory
            current_qty = 500  # Default
            init_inv = self._topology.initial_inventory.get(dc_name, {})
            current_qty = init_inv.get(str(p.id), current_qty)

            shrunk_qty = int(current_qty * (1 - profile.inventory_shrink_pct))

            rows.append([
                str(p.id),
                dc_name,
                '0001',
                str(shrunk_qty),
                '0',
                '0',
            ])

        return rows

    # ── Utility ──

    @staticmethod
    def _rows_to_csv(rows: List[List[str]]) -> str:
        """Convert list of rows to CSV string."""
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
        for row in rows:
            writer.writerow(row)
        return output.getvalue()
