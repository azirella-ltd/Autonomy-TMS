"""
SCP → TMS Food Dist ETL Snapshot Extractor

Reads from the SCP read-only role (`tms_reader`) and stages the rows the
Food Dist TMS overlay needs into TMS-side `tms_src_scp_*` tables.

Design notes:
- One-way pull. SCP is read-only.
- Truncate-and-reload semantics — staging is a snapshot, not a CDC stream.
- Identifier columns are kept as TEXT so SCP id types (int / String(100))
  pass through without coercion. Overlay treats them as opaque keys.
- Read transaction wraps every fetch with `SET TRANSACTION READ ONLY` as
  belt-and-suspenders alongside the role grant.

If SCP Food Dist is reseeded, this extractor must be re-run before the
overlay generator, or the overlay will reference stale SCP IDs.
See memory: project_food_dist_tms_etl.md
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import (
    Column, DateTime, Date, Double, Index, Integer, JSON, MetaData,
    String, Table, Text, create_engine, text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


# ============================================================================
# Staging schema — TMS-side `tms_src_scp_*` tables
# ============================================================================
#
# Defined as Core-level Table objects (not ORM models) so we don't drag the
# staging tables into the main mapper graph and risk relationship collisions.
# Schema is deliberately denormalized — staging is a flat snapshot, the
# overlay generator does the joining.

_meta = MetaData()


tms_src_scp_config = Table(
    "tms_src_scp_config", _meta,
    Column("scp_config_id", Integer, primary_key=True),
    Column("name", Text, nullable=False),
    Column("description", Text),
    Column("scp_tenant_id", Integer),
    Column("snapshot_at", DateTime, default=datetime.utcnow, nullable=False),
)

tms_src_scp_site = Table(
    "tms_src_scp_site", _meta,
    Column("scp_site_id", Integer, primary_key=True),
    Column("scp_config_id", Integer, nullable=False, index=True),
    Column("name", Text, nullable=False),
    Column("type", Text),
    Column("master_type", Text),
    Column("is_external", Integer),  # bool as 0/1
    Column("scp_trading_partner_id", Integer),
    Column("latitude", Double),
    Column("longitude", Double),
    Column("attributes", JSON),
    Column("snapshot_at", DateTime, default=datetime.utcnow, nullable=False),
)

tms_src_scp_trading_partner = Table(
    "tms_src_scp_trading_partner", _meta,
    Column("scp_partner_id", Integer, primary_key=True),
    Column("scp_config_id", Integer, index=True),
    Column("name", Text),
    Column("partner_type", Text),
    Column("postal_code", Text),
    Column("country", Text),
    Column("attributes", JSON),
    Column("snapshot_at", DateTime, default=datetime.utcnow, nullable=False),
)

tms_src_scp_lane = Table(
    "tms_src_scp_lane", _meta,
    Column("scp_lane_id", Integer, primary_key=True),
    Column("scp_config_id", Integer, nullable=False, index=True),
    Column("from_site_id", Integer),
    Column("to_site_id", Integer),
    Column("from_partner_id", Integer),
    Column("to_partner_id", Integer),
    Column("transit_time_days", Double),
    Column("snapshot_at", DateTime, default=datetime.utcnow, nullable=False),
)

tms_src_scp_product = Table(
    "tms_src_scp_product", _meta,
    Column("scp_product_id", Text, primary_key=True),
    Column("scp_config_id", Integer, index=True),
    Column("name", Text),
    Column("product_group", Text),
    Column("temperature_category", Text),  # frozen / refrigerated / dry
    Column("unit_size", Text),
    Column("cases_per_pallet", Integer),
    Column("attributes", JSON),
    Column("snapshot_at", DateTime, default=datetime.utcnow, nullable=False),
)

tms_src_scp_shipment = Table(
    "tms_src_scp_shipment", _meta,
    Column("scp_shipment_id", Text, primary_key=True),
    Column("scp_config_id", Integer, nullable=False, index=True),
    Column("scp_order_id", Text, index=True),
    Column("scp_product_id", Text, index=True),
    Column("quantity", Double),
    Column("uom", Text),
    Column("from_site_id", Integer, index=True),
    Column("to_site_id", Integer, index=True),
    Column("scp_lane_id", Integer),
    Column("status", Text),
    Column("ship_date", DateTime, index=True),
    Column("expected_delivery_date", DateTime),
    Column("actual_delivery_date", DateTime),
    Column("scp_carrier_id", Text),
    Column("scp_carrier_name", Text),
    Column("snapshot_at", DateTime, default=datetime.utcnow, nullable=False),
    Index("idx_scp_shipment_date_lane", "ship_date", "from_site_id", "to_site_id"),
)

tms_src_scp_outbound_order_line = Table(
    "tms_src_scp_outbound_order_line", _meta,
    Column("scp_line_id", Integer, primary_key=True),
    Column("scp_config_id", Integer, nullable=False, index=True),
    Column("scp_order_id", Text, index=True),
    Column("scp_product_id", Text, index=True),
    Column("quantity", Double),
    Column("requested_date", DateTime),
    Column("from_site_id", Integer),
    Column("to_site_id", Integer),
    Column("snapshot_at", DateTime, default=datetime.utcnow, nullable=False),
)

tms_src_scp_inbound_order_line = Table(
    "tms_src_scp_inbound_order_line", _meta,
    Column("scp_line_id", Integer, primary_key=True),
    Column("scp_config_id", Integer, nullable=False, index=True),
    Column("scp_order_id", Text, index=True),
    Column("scp_product_id", Text, index=True),
    Column("quantity", Double),
    Column("requested_date", DateTime),
    Column("from_partner_id", Integer),
    Column("to_site_id", Integer),
    Column("snapshot_at", DateTime, default=datetime.utcnow, nullable=False),
)


def create_staging_tables(tms_engine: Engine) -> None:
    """Idempotent — creates `tms_src_scp_*` tables if not present."""
    _meta.create_all(tms_engine, checkfirst=True)


# ============================================================================
# Extractor
# ============================================================================

@dataclass
class ExtractStats:
    config_rows: int = 0
    sites: int = 0
    trading_partners: int = 0
    lanes: int = 0
    products: int = 0
    shipments: int = 0
    outbound_lines: int = 0
    inbound_lines: int = 0


class FoodDistExtractor:
    """
    Pulls the Food Dist Demo SCP supply chain config and its associated
    history into TMS staging tables. Idempotent: truncates each `tms_src_scp_*`
    table at start, then inserts fresh.

    Accepts a config name (default 'Food Dist Demo' per Trevor) so the
    same extractor works for any SCP config without code changes.
    """

    DEFAULT_CONFIG_NAME = "Food Dist Demo"

    def __init__(
        self,
        scp_engine: Engine,
        tms_session: Session,
        *,
        scp_config_name: str = DEFAULT_CONFIG_NAME,
    ):
        self.scp_engine = scp_engine
        self.tms = tms_session
        self.scp_config_name = scp_config_name
        self._scp_config_id: Optional[int] = None

    # -----------------------------------------------------------------
    # Top-level entry
    # -----------------------------------------------------------------

    def run(self) -> ExtractStats:
        stats = ExtractStats()
        self._truncate_staging()
        with self.scp_engine.connect() as scp_conn:
            scp_conn.execute(text("SET TRANSACTION READ ONLY"))
            self._scp_config_id = self._resolve_config_id(scp_conn)
            stats.config_rows = self._extract_config(scp_conn)
            stats.sites = self._extract_sites(scp_conn)
            stats.trading_partners = self._extract_trading_partners(scp_conn)
            stats.lanes = self._extract_lanes(scp_conn)
            stats.products = self._extract_products(scp_conn)
            stats.shipments = self._extract_shipments(scp_conn)
            stats.outbound_lines = self._extract_outbound_lines(scp_conn)
            stats.inbound_lines = self._extract_inbound_lines(scp_conn)
        self.tms.commit()
        logger.info("Food Dist SCP→TMS ETL complete: %s", stats)
        return stats

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    def _truncate_staging(self) -> None:
        # CASCADE because shipments reference sites; safe since these are
        # snapshot tables with no external FKs.
        for tbl in (
            "tms_src_scp_inbound_order_line",
            "tms_src_scp_outbound_order_line",
            "tms_src_scp_shipment",
            "tms_src_scp_lane",
            "tms_src_scp_product",
            "tms_src_scp_trading_partner",
            "tms_src_scp_site",
            "tms_src_scp_config",
        ):
            self.tms.execute(text(f"TRUNCATE TABLE {tbl} RESTART IDENTITY CASCADE"))

    def _resolve_config_id(self, scp_conn) -> int:
        row = scp_conn.execute(
            text("SELECT id FROM supply_chain_configs WHERE name = :n LIMIT 1"),
            {"n": self.scp_config_name},
        ).first()
        if row is None:
            raise RuntimeError(
                f"SCP config '{self.scp_config_name}' not found. "
                f"Available: {self._list_configs(scp_conn)}"
            )
        return row[0]

    @staticmethod
    def _list_configs(scp_conn) -> List[str]:
        return [r[0] for r in scp_conn.execute(
            text("SELECT name FROM supply_chain_configs ORDER BY id")
        ).all()]

    def _bulk_insert(self, table: Table, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        # SQLAlchemy 2.0 Core insert in batches
        BATCH = 1000
        for i in range(0, len(rows), BATCH):
            self.tms.execute(table.insert(), rows[i : i + BATCH])
        return len(rows)

    # -----------------------------------------------------------------
    # Per-table extraction
    # -----------------------------------------------------------------

    def _extract_config(self, scp_conn) -> int:
        row = scp_conn.execute(
            text("SELECT id, name, description, tenant_id "
                 "FROM supply_chain_configs WHERE id = :i"),
            {"i": self._scp_config_id},
        ).mappings().first()
        return self._bulk_insert(tms_src_scp_config, [{
            "scp_config_id": row["id"],
            "name": row["name"],
            "description": row.get("description"),
            "scp_tenant_id": row.get("tenant_id"),
        }])

    def _extract_sites(self, scp_conn) -> int:
        rows = scp_conn.execute(
            text("""
                SELECT id, name, type, master_type, is_external,
                       trading_partner_id, latitude, longitude, attributes
                FROM site WHERE config_id = :c
            """),
            {"c": self._scp_config_id},
        ).mappings().all()
        return self._bulk_insert(tms_src_scp_site, [{
            "scp_site_id": r["id"],
            "scp_config_id": self._scp_config_id,
            "name": r["name"],
            "type": r["type"],
            "master_type": r.get("master_type"),
            "is_external": 1 if r.get("is_external") else 0,
            "scp_trading_partner_id": r.get("trading_partner_id"),
            "latitude": r.get("latitude"),
            "longitude": r.get("longitude"),
            "attributes": r.get("attributes"),
        } for r in rows])

    def _extract_trading_partners(self, scp_conn) -> int:
        # Trading partners aren't strictly scoped to config; pull those referenced
        # by Food Dist sites + lanes.
        rows = scp_conn.execute(
            text("""
                SELECT DISTINCT tp._id AS id, tp.name, tp.partner_type,
                       tp.postal_code, tp.country
                FROM trading_partners tp
                JOIN site s ON s.trading_partner_id = tp._id
                WHERE s.config_id = :c
            """),
            {"c": self._scp_config_id},
        ).mappings().all()
        return self._bulk_insert(tms_src_scp_trading_partner, [{
            "scp_partner_id": r["id"],
            "scp_config_id": self._scp_config_id,
            "name": r.get("name"),
            "partner_type": r.get("partner_type"),
            "postal_code": r.get("postal_code"),
            "country": r.get("country"),
        } for r in rows])

    def _extract_lanes(self, scp_conn) -> int:
        rows = scp_conn.execute(
            text("""
                SELECT id, from_site_id, to_site_id,
                       from_partner_id, to_partner_id
                FROM transportation_lane WHERE config_id = :c
            """),
            {"c": self._scp_config_id},
        ).mappings().all()
        return self._bulk_insert(tms_src_scp_lane, [{
            "scp_lane_id": r["id"],
            "scp_config_id": self._scp_config_id,
            "from_site_id": r.get("from_site_id"),
            "to_site_id": r.get("to_site_id"),
            "from_partner_id": r.get("from_partner_id"),
            "to_partner_id": r.get("to_partner_id"),
        } for r in rows])

    def _extract_products(self, scp_conn) -> int:
        # Food Dist's product table includes attributes JSON with temperature
        # category. SCP-side schema may vary; defensive col list.
        rows = scp_conn.execute(
            text("""
                SELECT id, name, product_group, attributes
                FROM product WHERE config_id = :c
            """),
            {"c": self._scp_config_id},
        ).mappings().all()
        out = []
        for r in rows:
            attrs = r.get("attributes") or {}
            out.append({
                "scp_product_id": str(r["id"]),
                "scp_config_id": self._scp_config_id,
                "name": r.get("name"),
                "product_group": r.get("product_group"),
                "temperature_category": attrs.get("temperature_category")
                                        or attrs.get("temp_category"),
                "unit_size": attrs.get("unit_size"),
                "cases_per_pallet": attrs.get("cases_per_pallet"),
                "attributes": attrs,
            })
        return self._bulk_insert(tms_src_scp_product, out)

    def _extract_shipments(self, scp_conn) -> int:
        rows = scp_conn.execute(
            text("""
                SELECT id, order_id, product_id, quantity, uom,
                       from_site_id, to_site_id, transportation_lane_id,
                       status, ship_date, expected_delivery_date,
                       actual_delivery_date, carrier_id, carrier_name
                FROM shipment WHERE config_id = :c
            """),
            {"c": self._scp_config_id},
        ).mappings().all()
        return self._bulk_insert(tms_src_scp_shipment, [{
            "scp_shipment_id": str(r["id"]),
            "scp_config_id": self._scp_config_id,
            "scp_order_id": str(r["order_id"]) if r.get("order_id") else None,
            "scp_product_id": str(r["product_id"]) if r.get("product_id") else None,
            "quantity": r.get("quantity"),
            "uom": r.get("uom"),
            "from_site_id": r.get("from_site_id"),
            "to_site_id": r.get("to_site_id"),
            "scp_lane_id": r.get("transportation_lane_id"),
            "status": r.get("status"),
            "ship_date": r.get("ship_date"),
            "expected_delivery_date": r.get("expected_delivery_date"),
            "actual_delivery_date": r.get("actual_delivery_date"),
            "scp_carrier_id": r.get("carrier_id"),
            "scp_carrier_name": r.get("carrier_name"),
        } for r in rows])

    def _extract_outbound_lines(self, scp_conn) -> int:
        rows = scp_conn.execute(
            text("""
                SELECT ol.id, ol.order_id, ol.product_id, ol.quantity,
                       ol.requested_date, oo.from_site_id, oo.to_site_id
                FROM outbound_order_line ol
                JOIN outbound_order oo ON ol.order_id = oo.id
                WHERE oo.config_id = :c
            """),
            {"c": self._scp_config_id},
        ).mappings().all()
        return self._bulk_insert(tms_src_scp_outbound_order_line, [{
            "scp_line_id": r["id"],
            "scp_config_id": self._scp_config_id,
            "scp_order_id": str(r["order_id"]) if r.get("order_id") else None,
            "scp_product_id": str(r["product_id"]) if r.get("product_id") else None,
            "quantity": r.get("quantity"),
            "requested_date": r.get("requested_date"),
            "from_site_id": r.get("from_site_id"),
            "to_site_id": r.get("to_site_id"),
        } for r in rows])

    def _extract_inbound_lines(self, scp_conn) -> int:
        rows = scp_conn.execute(
            text("""
                SELECT il.id, il.order_id, il.product_id, il.quantity,
                       il.requested_date, io.from_partner_id, io.to_site_id
                FROM inbound_order_line il
                JOIN inbound_order io ON il.order_id = io.id
                WHERE io.config_id = :c
            """),
            {"c": self._scp_config_id},
        ).mappings().all()
        return self._bulk_insert(tms_src_scp_inbound_order_line, [{
            "scp_line_id": r["id"],
            "scp_config_id": self._scp_config_id,
            "scp_order_id": str(r["order_id"]) if r.get("order_id") else None,
            "scp_product_id": str(r["product_id"]) if r.get("product_id") else None,
            "quantity": r.get("quantity"),
            "requested_date": r.get("requested_date"),
            "from_partner_id": r.get("from_partner_id"),
            "to_site_id": r.get("to_site_id"),
        } for r in rows])


# ============================================================================
# Convenience constructor
# ============================================================================

def build_scp_engine(scp_db_url: str) -> Engine:
    """Create a read-only SQLAlchemy engine for SCP. Belt and suspenders:
    - role grants are READ ONLY (set up by SCP DBA)
    - we explicitly issue `SET TRANSACTION READ ONLY` on each connection
    - pool is small; this is batch ETL, not a hot path
    """
    return create_engine(
        scp_db_url,
        pool_size=2,
        max_overflow=0,
        pool_pre_ping=True,
        connect_args={"options": "-c default_transaction_read_only=on"},
    )
