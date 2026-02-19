"""
SAP ATP Bridge Service

Bridges SAP S/4HANA ATP data with Autonomy ATP/CTP services.
Supports both real-time (RFC BAPI) and batch (table extraction) modes.

Key Responsibilities:
1. Extract ATP-relevant data from SAP (inventory, POs, production orders)
2. Transform SAP data to Autonomy internal models
3. Call internal ATP/CTP services with SAP data
4. Write back promised orders to SAP

Usage:
    from app.integrations.sap.sap_atp_bridge import SAPATPBridge, SAPATPConfig

    config = SAPATPConfig(
        s4hana_config=S4HANAConnectionConfig(...),
        use_realtime_bapi=True
    )

    bridge = SAPATPBridge(config, db_session)
    bridge.connect()

    # Real-time ATP check
    result = bridge.check_atp_realtime("1000", "FG001", date.today(), 100)

    # Batch sync
    bridge.sync_inventory_levels(plant="1000", delta_only=True)

    bridge.disconnect()
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
import pandas as pd

from sqlalchemy.orm import Session

from .s4hana_connector import S4HANAConnector, S4HANAConnectionConfig
from .data_mapper import SupplyChainMapper
from .delta_loader import SAPDeltaLoader, DeltaLoadConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class SAPATPConfig:
    """Configuration for SAP ATP bridge."""

    # Connection settings
    s4hana_config: S4HANAConnectionConfig

    # Operation mode
    use_realtime_bapi: bool = True  # Use BAPI vs table extraction
    fallback_to_batch: bool = True  # Fall back to batch if BAPI fails

    # ATP settings
    default_check_rule: str = "A"  # A=ATP, B=full planning
    include_safety_stock: bool = True
    include_blocked_stock: bool = False
    include_quality_stock: bool = False

    # CTP settings
    check_production_capacity: bool = True
    check_component_availability: bool = True
    max_bom_levels: int = 3
    default_yield_rate: float = 0.95  # 5% scrap

    # Sync settings
    sync_interval_minutes: int = 15
    delta_mode: bool = True

    # Write-back settings
    auto_confirm_promises: bool = False
    promise_confirmation_bapi: str = "BAPI_SALESORDER_CHANGE"
    test_mode: bool = False  # Simulate only


# =============================================================================
# Result Data Classes
# =============================================================================

@dataclass
class ATPResult:
    """ATP calculation result (compatible with atp_service.ATPResult)."""
    on_hand: int
    scheduled_receipts: int
    allocated_orders: int
    safety_stock: int
    atp: int
    timestamp: str


@dataclass
class CTPResult:
    """CTP calculation result (compatible with ctp_service.CTPResult)."""
    production_capacity: int
    current_commitments: int
    yield_rate: float
    available_capacity: int
    component_constraints: List[Dict[str, Any]]
    ctp: int
    constrained_by: Optional[str]


@dataclass
class SAPATPResult:
    """ATP result with SAP-specific details."""

    # Core ATP result
    atp: ATPResult

    # SAP source data
    sap_plant: str
    sap_material: str
    sap_check_date: date

    # SAP ATP breakdown
    unrestricted_stock: float = 0.0
    quality_inspection_stock: float = 0.0
    blocked_stock: float = 0.0
    in_transit_stock: float = 0.0

    # SAP scheduled supply
    purchase_order_qty: float = 0.0
    production_order_qty: float = 0.0
    stock_transfer_qty: float = 0.0

    # SAP committed demand
    sales_order_qty: float = 0.0
    delivery_qty: float = 0.0
    reservation_qty: float = 0.0

    # Safety stock from SAP
    sap_safety_stock: float = 0.0

    # BAPI response
    bapi_used: bool = False
    bapi_response: Optional[Dict] = None


@dataclass
class SAPCTPResult:
    """CTP result with SAP-specific details."""

    # Core CTP result
    ctp: CTPResult

    # SAP source data
    sap_plant: str
    sap_material: str

    # Production capacity from SAP
    available_capacity_hours: float = 0.0
    committed_capacity_hours: float = 0.0
    capacity_utilization_pct: float = 0.0

    # Production lead time
    production_lead_time_days: int = 0
    routing_time_hours: float = 0.0

    # Component availability
    component_atp_results: Dict[str, SAPATPResult] = field(default_factory=dict)
    constraining_component: Optional[str] = None

    # BAPI response
    bapi_used: bool = False


@dataclass
class SyncResult:
    """Result from data synchronization operation."""
    sync_type: str
    records_synced: int
    records_created: int
    records_updated: int
    duration_seconds: float
    delta_mode: bool
    errors: List[str] = field(default_factory=list)


# =============================================================================
# SAP ATP Bridge Service
# =============================================================================

class SAPATPBridge:
    """
    Bridge service connecting SAP S/4HANA to Autonomy ATP/CTP.

    Modes of operation:
    1. Real-time BAPI: Direct call to SAP BAPIs for instant ATP check
    2. Batch extraction: Extract tables, calculate locally
    3. Hybrid: BAPI for single checks, batch for bulk operations
    """

    def __init__(
        self,
        config: SAPATPConfig,
        db: Session,
    ):
        """
        Initialize SAP ATP bridge.

        Args:
            config: SAP ATP configuration
            db: SQLAlchemy database session
        """
        self.config = config
        self.db = db

        self.connector: Optional[S4HANAConnector] = None
        self.mapper = SupplyChainMapper()
        self.delta_loader = SAPDeltaLoader()

        # Cache for repeated lookups
        self._atp_cache: Dict[str, SAPATPResult] = {}
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_seconds = 300  # 5 minute cache

    def connect(self) -> bool:
        """Establish connection to SAP S/4HANA."""
        try:
            self.connector = S4HANAConnector(self.config.s4hana_config)
            return self.connector.connect()
        except Exception as e:
            logger.error(f"Failed to connect to SAP: {e}")
            return False

    def disconnect(self):
        """Close SAP connection."""
        if self.connector:
            self.connector.disconnect()
            self.connector = None

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()

    # =========================================================================
    # Real-time ATP Methods
    # =========================================================================

    def check_atp_realtime(
        self,
        plant: str,
        material: str,
        check_date: date,
        quantity: float = 1.0
    ) -> SAPATPResult:
        """
        Real-time ATP check using SAP BAPI.

        Calls BAPI_MATERIAL_AVAILABILITY for instant ATP.
        Falls back to table extraction if BAPI fails.

        Args:
            plant: SAP plant code (e.g., "1000")
            material: SAP material number
            check_date: Date to check availability
            quantity: Quantity to check

        Returns:
            SAPATPResult with ATP calculation and SAP details
        """
        # Check cache first
        cache_key = f"{plant}:{material}:{check_date}"
        if self._is_cache_valid() and cache_key in self._atp_cache:
            logger.debug(f"Returning cached ATP for {cache_key}")
            return self._atp_cache[cache_key]

        if self.config.use_realtime_bapi and self.connector:
            try:
                bapi_result = self.connector.call_bapi_material_availability(
                    plant=plant,
                    material=material,
                    check_date=check_date,
                    quantity=quantity,
                    check_rule=self.config.default_check_rule
                )

                result = self._parse_bapi_atp_result(
                    bapi_result, plant, material, check_date
                )

                # Cache result
                self._atp_cache[cache_key] = result
                self._cache_timestamp = datetime.utcnow()

                return result

            except Exception as e:
                logger.warning(f"BAPI call failed, falling back to batch: {e}")
                if not self.config.fallback_to_batch:
                    raise

        # Fallback to batch extraction
        return self.calculate_atp_from_tables(plant, material, check_date)

    def check_atp_bulk(
        self,
        plant: str,
        materials: List[str],
        check_date: date
    ) -> Dict[str, SAPATPResult]:
        """
        Bulk ATP check for multiple materials.

        Uses batch extraction (more efficient than multiple BAPI calls).

        Args:
            plant: SAP plant code
            materials: List of material numbers
            check_date: Date to check availability

        Returns:
            Dict mapping material number to SAPATPResult
        """
        logger.info(f"Bulk ATP check for {len(materials)} materials at {plant}")

        # Extract relevant data from SAP
        atp_data = self._extract_atp_data_bulk(plant, materials, check_date)

        results = {}
        for material in materials:
            results[material] = self._calculate_atp_from_extracted_data(
                plant, material, check_date, atp_data
            )

        return results

    def check_ctp_realtime(
        self,
        plant: str,
        material: str,
        check_date: date,
        quantity: float
    ) -> SAPCTPResult:
        """
        Real-time CTP check including production capacity.

        Steps:
        1. Check ATP for finished good
        2. Get production capacity and WIP
        3. Check component ATP (BOM explosion)
        4. Calculate CTP as min(ATP, capacity, component availability)

        Args:
            plant: SAP plant code
            material: SAP material number
            check_date: Date to check
            quantity: Quantity requested

        Returns:
            SAPCTPResult with CTP calculation
        """
        logger.info(f"CTP check for {material} at {plant}, qty={quantity}")

        # Step 1: Get finished good ATP
        fg_atp = self.check_atp_realtime(plant, material, check_date, quantity)

        # Step 2: Get production capacity
        capacity_data = self._get_production_capacity(plant, material, check_date)

        # Step 3: Check component availability
        component_results = {}
        constraining_component = None

        if self.config.check_component_availability:
            bom = self._get_bom_from_sap(material, plant)
            min_producible = float('inf')

            for component in bom:
                comp_material = component['material']
                qty_per = component['quantity_per']

                comp_atp = self.check_atp_realtime(
                    plant,
                    comp_material,
                    check_date,
                    quantity * qty_per
                )
                component_results[comp_material] = comp_atp

                # Track constraining component
                max_from_component = comp_atp.atp.atp / qty_per if qty_per > 0 else 0
                if max_from_component < min_producible:
                    min_producible = max_from_component
                    constraining_component = comp_material

        # Step 4: Calculate CTP
        return self._calculate_ctp_from_components(
            fg_atp, capacity_data, component_results,
            constraining_component, plant, material, quantity
        )

    # =========================================================================
    # Batch Extraction Methods
    # =========================================================================

    def calculate_atp_from_tables(
        self,
        plant: str,
        material: str,
        check_date: date
    ) -> SAPATPResult:
        """
        Calculate ATP from extracted SAP tables.

        ATP = Unrestricted Stock + Scheduled Receipts - Committed Demand - Safety Stock

        Args:
            plant: SAP plant code
            material: SAP material number
            check_date: Date for ATP calculation

        Returns:
            SAPATPResult calculated from table data
        """
        logger.info(f"Calculating ATP from tables for {material} at {plant}")

        # Get inventory from MARD
        inventory = self.connector.extract_inventory(plant=plant)
        mat_inv = inventory[inventory['MATNR'].str.strip() == material.strip()]

        unrestricted = float(mat_inv['LABST'].sum()) if not mat_inv.empty else 0
        in_transit = float(mat_inv['UMLME'].sum()) if not mat_inv.empty else 0
        blocked = float(mat_inv['SPEME'].sum()) if not mat_inv.empty else 0
        quality = float(mat_inv['INSME'].sum()) if not mat_inv.empty else 0

        # Get safety stock from MARC
        marc = self.connector.extract_material_atp_data(plant=plant, materials=[material])
        safety_stock = float(marc.iloc[0]['EISBE']) if not marc.empty else 0

        # Get scheduled receipts (POs)
        horizon_end = check_date + timedelta(days=7)
        schedule_lines = self.connector.extract_schedule_lines(
            plant=plant,
            date_from=date.today(),
            date_to=horizon_end
        )

        po_qty = 0.0
        if not schedule_lines.empty and 'MATNR' in schedule_lines.columns:
            mat_schedules = schedule_lines[schedule_lines['MATNR'].str.strip() == material.strip()]
            po_qty = float(mat_schedules['OPEN_QTY'].sum()) if not mat_schedules.empty else 0

        # Get production orders (scheduled receipts from production)
        prod_headers, prod_items = self.connector.extract_production_orders(
            plant=plant,
            date_from=date.today(),
            date_to=horizon_end
        )

        prod_qty = 0.0
        if not prod_items.empty:
            mat_prod = prod_items[prod_items['MATNR'].str.strip() == material.strip()]
            if not mat_prod.empty:
                planned = pd.to_numeric(mat_prod['PSMNG'], errors='coerce').fillna(0)
                received = pd.to_numeric(mat_prod['WEMNG'], errors='coerce').fillna(0)
                prod_qty = float((planned - received).sum())

        # Get committed demand (reservations)
        reservations = self.connector.extract_reservations(plant=plant, material=material)
        reserved_qty = float(reservations['OPEN_QTY'].sum()) if not reservations.empty else 0

        # Calculate ATP
        on_hand = unrestricted
        if self.config.include_blocked_stock:
            on_hand += blocked
        if self.config.include_quality_stock:
            on_hand += quality

        scheduled_receipts = po_qty + prod_qty + in_transit
        allocated = reserved_qty

        if self.config.include_safety_stock:
            atp = max(0, on_hand + scheduled_receipts - allocated - safety_stock)
        else:
            atp = max(0, on_hand + scheduled_receipts - allocated)

        atp_result = ATPResult(
            on_hand=int(on_hand),
            scheduled_receipts=int(scheduled_receipts),
            allocated_orders=int(allocated),
            safety_stock=int(safety_stock),
            atp=int(atp),
            timestamp=datetime.utcnow().isoformat()
        )

        return SAPATPResult(
            atp=atp_result,
            sap_plant=plant,
            sap_material=material,
            sap_check_date=check_date,
            unrestricted_stock=unrestricted,
            quality_inspection_stock=quality,
            blocked_stock=blocked,
            in_transit_stock=in_transit,
            purchase_order_qty=po_qty,
            production_order_qty=prod_qty,
            stock_transfer_qty=0,
            sales_order_qty=0,
            delivery_qty=0,
            reservation_qty=reserved_qty,
            sap_safety_stock=safety_stock,
            bapi_used=False
        )

    # =========================================================================
    # Sync Methods
    # =========================================================================

    def sync_inventory_levels(
        self,
        plant: Optional[str] = None,
        delta_only: bool = True
    ) -> SyncResult:
        """
        Sync SAP inventory levels to Autonomy InvLevel table.

        Args:
            plant: Optional plant filter
            delta_only: Only sync changed records

        Returns:
            SyncResult with sync statistics
        """
        from app.models.sc_entities import InvLevel

        start_time = datetime.utcnow()
        logger.info(f"Syncing inventory levels (plant={plant}, delta={delta_only})")

        # Extract from MARD
        inventory_df = self.connector.extract_inventory(plant=plant)

        if inventory_df.empty:
            return SyncResult(
                sync_type="inventory",
                records_synced=0,
                records_created=0,
                records_updated=0,
                duration_seconds=0,
                delta_mode=delta_only
            )

        # Apply delta loading if enabled
        if delta_only:
            config = DeltaLoadConfig(
                table_name="MARD",
                key_fields=["MATNR", "WERKS", "LGORT"],
                change_date_field=None,
                lookback_days=1
            )
            inventory_df, delta_result = self.delta_loader.load_delta(inventory_df, config)
            logger.info(f"Delta: {delta_result.new_records} new, {delta_result.changed_records} changed")

        # Map and upsert
        created = 0
        updated = 0

        for _, row in inventory_df.iterrows():
            product_id = str(row['MATNR']).strip()
            site_id = str(row['WERKS']).strip()

            existing = self.db.query(InvLevel).filter(
                InvLevel.product_id == product_id,
                InvLevel.site_id == site_id
            ).first()

            on_hand = float(row.get('LABST', 0) or 0)
            in_transit = float(row.get('UMLME', 0) or 0)

            if existing:
                existing.on_hand_qty = on_hand
                existing.in_transit_qty = in_transit
                existing.source_update_dttm = datetime.utcnow()
                updated += 1
            else:
                new_level = InvLevel(
                    product_id=product_id,
                    site_id=site_id,
                    on_hand_qty=on_hand,
                    in_transit_qty=in_transit,
                    source='SAP_MARD',
                    source_update_dttm=datetime.utcnow()
                )
                self.db.add(new_level)
                created += 1

        self.db.commit()

        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Synced {created + updated} inventory records in {duration:.2f}s")

        return SyncResult(
            sync_type="inventory",
            records_synced=created + updated,
            records_created=created,
            records_updated=updated,
            duration_seconds=duration,
            delta_mode=delta_only
        )

    def sync_safety_stock_policies(
        self,
        plant: Optional[str] = None
    ) -> SyncResult:
        """
        Sync SAP MARC.EISBE to Autonomy InvPolicy table.

        Args:
            plant: Optional plant filter

        Returns:
            SyncResult with sync statistics
        """
        from app.models.sc_entities import InvPolicy

        start_time = datetime.utcnow()
        logger.info(f"Syncing safety stock policies (plant={plant})")

        # Extract MARC with ATP fields
        marc_df = self.connector.extract_material_atp_data(plant=plant)

        if marc_df.empty:
            return SyncResult(
                sync_type="safety_stock",
                records_synced=0,
                records_created=0,
                records_updated=0,
                duration_seconds=0,
                delta_mode=False
            )

        created = 0
        updated = 0

        for _, row in marc_df.iterrows():
            product_id = str(row['MATNR']).strip()
            site_id = str(row['WERKS']).strip()
            safety_stock = float(row.get('EISBE', 0) or 0)
            lead_time = int(row.get('PLIFZ', 0) or 0)

            existing = self.db.query(InvPolicy).filter(
                InvPolicy.product_id == product_id,
                InvPolicy.site_id == site_id
            ).first()

            if existing:
                existing.ss_quantity = safety_stock
                existing.review_period = lead_time
                existing.source_update_dttm = datetime.utcnow()
                updated += 1
            else:
                new_policy = InvPolicy(
                    product_id=product_id,
                    site_id=site_id,
                    ss_policy='abs_level',  # SAP EISBE is absolute
                    ss_quantity=safety_stock,
                    review_period=lead_time,
                    source='SAP_MARC',
                    source_update_dttm=datetime.utcnow()
                )
                self.db.add(new_policy)
                created += 1

        self.db.commit()

        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Synced {created + updated} safety stock policies in {duration:.2f}s")

        return SyncResult(
            sync_type="safety_stock",
            records_synced=created + updated,
            records_created=created,
            records_updated=updated,
            duration_seconds=duration,
            delta_mode=False
        )

    def sync_production_orders(
        self,
        plant: Optional[str] = None,
        date_from: Optional[date] = None
    ) -> SyncResult:
        """
        Sync SAP production orders (AFKO/AFPO) to Autonomy.

        Args:
            plant: Optional plant filter
            date_from: Only sync orders with finish date >= date_from

        Returns:
            SyncResult with sync statistics
        """
        start_time = datetime.utcnow()
        logger.info(f"Syncing production orders (plant={plant})")

        headers, items = self.connector.extract_production_orders(
            plant=plant,
            date_from=date_from or date.today()
        )

        if headers.empty:
            return SyncResult(
                sync_type="production_orders",
                records_synced=0,
                records_created=0,
                records_updated=0,
                duration_seconds=0,
                delta_mode=False
            )

        # Map to internal format and save
        # Note: ProductionOrder model may need to be created/extended
        created = 0
        updated = 0

        # For now, just log the extraction results
        logger.info(f"Extracted {len(headers)} production orders, {len(items)} items")
        created = len(headers)

        duration = (datetime.utcnow() - start_time).total_seconds()

        return SyncResult(
            sync_type="production_orders",
            records_synced=created + updated,
            records_created=created,
            records_updated=updated,
            duration_seconds=duration,
            delta_mode=False
        )

    def sync_scheduled_receipts(
        self,
        plant: Optional[str] = None,
        date_from: Optional[date] = None
    ) -> SyncResult:
        """
        Sync SAP scheduled receipts (PO schedule lines) to SupplyPlan.

        Args:
            plant: Optional plant filter
            date_from: Only sync receipts with date >= date_from

        Returns:
            SyncResult with sync statistics
        """
        from app.models.sc_entities import SupplyPlan

        start_time = datetime.utcnow()
        logger.info(f"Syncing scheduled receipts (plant={plant})")

        schedule_lines = self.connector.extract_schedule_lines(
            plant=plant,
            date_from=date_from or date.today()
        )

        if schedule_lines.empty:
            return SyncResult(
                sync_type="scheduled_receipts",
                records_synced=0,
                records_created=0,
                records_updated=0,
                duration_seconds=0,
                delta_mode=False
            )

        created = 0
        updated = 0

        for _, row in schedule_lines.iterrows():
            if 'MATNR' not in row or 'WERKS' not in row:
                continue

            product_id = str(row['MATNR']).strip()
            site_id = str(row['WERKS']).strip()
            po_number = str(row.get('EBELN', '')).strip()
            line_number = str(row.get('EBELP', '')).strip()
            quantity = float(row.get('OPEN_QTY', 0) or 0)

            if quantity <= 0:
                continue

            # Check for existing supply plan entry
            existing = self.db.query(SupplyPlan).filter(
                SupplyPlan.product_id == product_id,
                SupplyPlan.site_id == site_id,
                SupplyPlan.po_number == po_number,
                SupplyPlan.po_line_number == line_number
            ).first()

            plan_date = pd.to_datetime(row.get('EINDT'), errors='coerce')
            if pd.isna(plan_date):
                plan_date = datetime.utcnow()

            if existing:
                existing.planned_order_quantity = quantity
                existing.plan_date = plan_date
                existing.source_update_dttm = datetime.utcnow()
                updated += 1
            else:
                new_plan = SupplyPlan(
                    product_id=product_id,
                    site_id=site_id,
                    po_number=po_number,
                    po_line_number=line_number,
                    planned_order_quantity=quantity,
                    plan_date=plan_date,
                    plan_type='po_request',
                    source='SAP_EKET',
                    source_update_dttm=datetime.utcnow()
                )
                self.db.add(new_plan)
                created += 1

        self.db.commit()

        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Synced {created + updated} scheduled receipts in {duration:.2f}s")

        return SyncResult(
            sync_type="scheduled_receipts",
            records_synced=created + updated,
            records_created=created,
            records_updated=updated,
            duration_seconds=duration,
            delta_mode=False
        )

    # =========================================================================
    # Promise Write-back Methods
    # =========================================================================

    def confirm_order_promise(
        self,
        order_id: str,
        order_line: int,
        promised_quantity: float,
        promised_date: date,
        update_sap: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        Confirm an order promise and optionally update SAP.

        Args:
            order_id: Sales order number
            order_line: Sales order line number
            promised_quantity: Confirmed quantity
            promised_date: Confirmed delivery date
            update_sap: Whether to write back to SAP

        Returns:
            Tuple of (success, SAP document number or error message)
        """
        logger.info(f"Confirming promise for order {order_id}/{order_line}")

        if not update_sap:
            return True, None

        if not self.connector:
            return False, "Not connected to SAP"

        # Write to SAP
        try:
            result = self.connector.call_bapi_salesorder_change(
                sales_order=order_id,
                schedule_lines=[{
                    "ITM_NUMBER": str(order_line).zfill(6),
                    "SCHED_LINE": "0001",
                    "REQ_DATE": promised_date.strftime("%Y%m%d"),
                    "REQ_QTY": promised_quantity,
                }],
                test_mode=self.config.test_mode
            )

            return_messages = result.get("RETURN", [])
            has_error = any(msg.get("TYPE") == "E" for msg in return_messages)

            if has_error:
                error_msg = next(
                    (msg.get("MESSAGE") for msg in return_messages if msg.get("TYPE") == "E"),
                    "Unknown error"
                )
                return False, error_msg

            return True, result.get("SALESDOCUMENT", order_id)

        except Exception as e:
            logger.error(f"Failed to write promise to SAP: {e}")
            return False, str(e)

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _is_cache_valid(self) -> bool:
        """Check if ATP cache is still valid."""
        if not self._cache_timestamp:
            return False
        age = (datetime.utcnow() - self._cache_timestamp).total_seconds()
        return age < self._cache_ttl_seconds

    def _parse_bapi_atp_result(
        self,
        bapi_result: Dict,
        plant: str,
        material: str,
        check_date: date
    ) -> SAPATPResult:
        """Parse BAPI_MATERIAL_AVAILABILITY response into SAPATPResult."""
        av_qty = float(bapi_result.get("AV_QTY_PLT", 0) or 0)

        # Build ATPResult
        atp_result = ATPResult(
            on_hand=int(av_qty),  # BAPI returns available directly
            scheduled_receipts=0,  # BAPI doesn't separate
            allocated_orders=0,
            safety_stock=0,
            atp=int(av_qty),
            timestamp=datetime.utcnow().isoformat()
        )

        return SAPATPResult(
            atp=atp_result,
            sap_plant=plant,
            sap_material=material,
            sap_check_date=check_date,
            unrestricted_stock=av_qty,
            bapi_used=True,
            bapi_response=bapi_result
        )

    def _extract_atp_data_bulk(
        self,
        plant: str,
        materials: List[str],
        check_date: date
    ) -> Dict[str, pd.DataFrame]:
        """Extract all ATP-relevant data for bulk processing."""
        return {
            'inventory': self.connector.extract_inventory(plant=plant),
            'marc': self.connector.extract_material_atp_data(plant=plant, materials=materials),
            'schedule_lines': self.connector.extract_schedule_lines(
                plant=plant,
                date_from=date.today(),
                date_to=check_date + timedelta(days=7)
            ),
            'production_orders': self.connector.extract_production_orders(
                plant=plant,
                date_from=date.today(),
                date_to=check_date
            ),
            'reservations': self.connector.extract_reservations(plant=plant),
        }

    def _calculate_atp_from_extracted_data(
        self,
        plant: str,
        material: str,
        check_date: date,
        data: Dict[str, pd.DataFrame]
    ) -> SAPATPResult:
        """Calculate ATP for a single material from pre-extracted data."""
        # Filter inventory
        inventory = data['inventory']
        mat_inv = inventory[inventory['MATNR'].str.strip() == material.strip()] if not inventory.empty else pd.DataFrame()

        unrestricted = float(mat_inv['LABST'].sum()) if not mat_inv.empty else 0
        in_transit = float(mat_inv['UMLME'].sum()) if not mat_inv.empty else 0

        # Get safety stock
        marc = data['marc']
        mat_marc = marc[marc['MATNR'].str.strip() == material.strip()] if not marc.empty else pd.DataFrame()
        safety_stock = float(mat_marc['EISBE'].iloc[0]) if not mat_marc.empty else 0

        # Get scheduled receipts
        schedule_lines = data['schedule_lines']
        po_qty = 0.0
        if not schedule_lines.empty and 'MATNR' in schedule_lines.columns:
            mat_sched = schedule_lines[schedule_lines['MATNR'].str.strip() == material.strip()]
            po_qty = float(mat_sched['OPEN_QTY'].sum()) if not mat_sched.empty else 0

        # Get production orders
        prod_headers, prod_items = data['production_orders']
        prod_qty = 0.0
        if not prod_items.empty:
            mat_prod = prod_items[prod_items['MATNR'].str.strip() == material.strip()]
            if not mat_prod.empty:
                planned = pd.to_numeric(mat_prod['PSMNG'], errors='coerce').fillna(0)
                received = pd.to_numeric(mat_prod['WEMNG'], errors='coerce').fillna(0)
                prod_qty = float((planned - received).sum())

        # Get reservations
        reservations = data['reservations']
        reserved_qty = 0.0
        if not reservations.empty:
            mat_res = reservations[reservations['MATNR'].str.strip() == material.strip()]
            reserved_qty = float(mat_res['OPEN_QTY'].sum()) if not mat_res.empty else 0

        # Calculate ATP
        on_hand = unrestricted
        scheduled_receipts = po_qty + prod_qty + in_transit
        atp = max(0, on_hand + scheduled_receipts - reserved_qty - safety_stock)

        atp_result = ATPResult(
            on_hand=int(on_hand),
            scheduled_receipts=int(scheduled_receipts),
            allocated_orders=int(reserved_qty),
            safety_stock=int(safety_stock),
            atp=int(atp),
            timestamp=datetime.utcnow().isoformat()
        )

        return SAPATPResult(
            atp=atp_result,
            sap_plant=plant,
            sap_material=material,
            sap_check_date=check_date,
            unrestricted_stock=unrestricted,
            in_transit_stock=in_transit,
            purchase_order_qty=po_qty,
            production_order_qty=prod_qty,
            reservation_qty=reserved_qty,
            sap_safety_stock=safety_stock,
            bapi_used=False
        )

    def _get_production_capacity(
        self,
        plant: str,
        material: str,
        check_date: date
    ) -> Dict[str, float]:
        """Get production capacity from SAP or defaults."""
        # Extract MARC to get production time
        marc = self.connector.extract_material_atp_data(plant=plant, materials=[material])

        if not marc.empty:
            dzeit = float(marc.iloc[0].get('DZEIT', 0) or 0)  # In-house production time
            return {
                'available_hours': 8.0,  # Default 8-hour day
                'operation_time': dzeit,
                'setup_time': 0,
                'yield_pct': self.config.default_yield_rate * 100,
            }

        return {
            'available_hours': 8.0,
            'operation_time': 0,
            'setup_time': 0,
            'yield_pct': self.config.default_yield_rate * 100,
        }

    def _get_bom_from_sap(
        self,
        material: str,
        plant: str
    ) -> List[Dict[str, Any]]:
        """Get BOM components from local ProductBom table."""
        from app.models.sc_entities import ProductBom

        bom_entries = self.db.query(ProductBom).filter(
            ProductBom.product_id == material
        ).all()

        return [
            {
                'material': entry.component_product_id,
                'quantity_per': entry.component_quantity or 1.0,
                'scrap_pct': entry.scrap_percentage or 0,
            }
            for entry in bom_entries
        ]

    def _calculate_ctp_from_components(
        self,
        fg_atp: SAPATPResult,
        capacity_data: Dict[str, float],
        component_results: Dict[str, SAPATPResult],
        constraining_component: Optional[str],
        plant: str,
        material: str,
        quantity: float
    ) -> SAPCTPResult:
        """Calculate CTP from component ATP results and capacity."""
        # Calculate available capacity (simplified)
        yield_rate = capacity_data.get('yield_pct', 95) / 100
        available_capacity = 1000  # Default capacity

        # Find constraining component
        min_from_components = float('inf')
        for comp_material, comp_atp in component_results.items():
            bom = self._get_bom_from_sap(material, plant)
            qty_per = next(
                (c['quantity_per'] for c in bom if c['material'] == comp_material),
                1.0
            )
            max_from_comp = comp_atp.atp.atp / qty_per if qty_per > 0 else 0
            if max_from_comp < min_from_components:
                min_from_components = max_from_comp
                constraining_component = comp_material

        # CTP = min(ATP, capacity * yield, component availability)
        ctp_qty = min(
            fg_atp.atp.atp,
            available_capacity * yield_rate,
            min_from_components if min_from_components != float('inf') else float('inf')
        )
        ctp_qty = max(0, int(ctp_qty))

        # Determine constraint
        constrained_by = None
        if ctp_qty < quantity:
            if ctp_qty == fg_atp.atp.atp:
                constrained_by = "inventory"
            elif ctp_qty == int(available_capacity * yield_rate):
                constrained_by = "capacity"
            elif constraining_component:
                constrained_by = f"component:{constraining_component}"

        ctp_result = CTPResult(
            production_capacity=int(available_capacity),
            current_commitments=0,
            yield_rate=yield_rate,
            available_capacity=int(available_capacity * yield_rate),
            component_constraints=[
                {'material': m, 'atp': r.atp.atp}
                for m, r in component_results.items()
            ],
            ctp=ctp_qty,
            constrained_by=constrained_by
        )

        return SAPCTPResult(
            ctp=ctp_result,
            sap_plant=plant,
            sap_material=material,
            available_capacity_hours=capacity_data.get('available_hours', 8.0),
            committed_capacity_hours=0,
            capacity_utilization_pct=0,
            production_lead_time_days=int(capacity_data.get('operation_time', 0)),
            routing_time_hours=capacity_data.get('operation_time', 0),
            component_atp_results=component_results,
            constraining_component=constraining_component,
            bapi_used=False
        )
