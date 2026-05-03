"""Integration tests for ProductLaneAggregator — exercise the SQL
JOIN + filter + upsert against an in-memory SQLite.

Companion to ``test_product_lane_aggregator.py`` (pure-logic tests):
the pure-logic suite covers ``_compute_shares`` math and validators;
this suite covers the SQL JOIN, period-filter, source-precedence
upsert, and config-id scoping that need a live database to validate.

**Local-environment caveat.** Running these against in-memory SQLite
requires the full Core auto-stubber harness (transitive FK targets,
relationship-target placeholders, configure-failure cache reset).
Even that machinery has edge cases — a Core ORM may declare a
relationship with an implicit ``primaryjoin`` that depends on
columns the stub doesn't have. These tests are gated on
``TMS_RUN_INTEGRATION_TESTS=1`` so local pytest doesn't fail on
those edge cases; CI sets the env var and runs them against a real
Postgres where the relationship resolution works correctly.

The heavy harness (eager master imports + auto-stubbers) is inlined
in this file rather than the directory's ``conftest.py`` so the
lighter pure-logic tests in this directory don't pay the
configure-mappers cost.

Same module-load pattern as the other powell substrate tests —
load the aggregator module via importlib so we don't trigger
``app.services.powell.__init__``'s heavy DB-bound side-effects.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from datetime import date

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("TMS_RUN_INTEGRATION_TESTS") != "1",
    reason=(
        "ProductLaneAggregator integration tests require a real Postgres "
        "(or a fully-resolved Core ORM registry). Set "
        "TMS_RUN_INTEGRATION_TESTS=1 in CI to enable. Pure-logic tests "
        "cover the math in test_product_lane_aggregator.py."
    ),
)


# ---------------------------------------------------------------------------
# Heavy harness — only fires when the env-gate is on.
# ---------------------------------------------------------------------------


if os.environ.get("TMS_RUN_INTEGRATION_TESTS") == "1":
    from sqlalchemy import Column, ForeignKey, Integer, String, Table

    from azirella_data_model.base import Base

    # Tenant / User stubs MUST be registered before master imports
    # because master.config.SupplyChainConfig declares
    # ``relationship("Tenant", back_populates="supply_chain_configs")``.
    if "tenants" not in Base.metadata.tables:
        class Tenant(Base):
            __tablename__ = "tenants"
            id = Column(Integer, primary_key=True)
            name = Column(String(255), nullable=True)

    if "users" not in Base.metadata.tables:
        class User(Base):
            __tablename__ = "users"
            id = Column(Integer, primary_key=True)

    # Eager-import master + transport_plan + simulation.scenario so
    # canonical classes register on Base.metadata before stubbers run.
    import azirella_data_model.master  # noqa: F401
    import azirella_data_model.simulation.scenario  # noqa: F401
    import azirella_data_model.transport_plan  # noqa: F401

    def _camel_to_snake(name: str) -> str:
        out = []
        for i, ch in enumerate(name):
            if ch.isupper() and i > 0 and not name[i - 1].isupper():
                out.append("_")
            out.append(ch.lower())
        return "".join(out)

    def _stub_unresolved_fk_targets() -> None:
        needed: set = set()
        existing = set(Base.metadata.tables.keys())
        for table in list(Base.metadata.tables.values()):
            for col in table.columns:
                for fk in col.foreign_keys:
                    target = fk.target_fullname
                    tbl_name = target.split(".", 1)[0]
                    if tbl_name not in existing:
                        needed.add(tbl_name)
        for tbl_name in sorted(needed):
            if tbl_name in Base.metadata.tables:
                continue
            Table(tbl_name, Base.metadata, Column("id", Integer, primary_key=True))

    def _stub_unresolved_relationship_targets() -> None:
        from sqlalchemy.orm import RelationshipProperty
        registry = Base.registry
        known = set(registry._class_registry.keys())
        needed: set = set()
        for entry in list(registry._class_registry.values()):
            mapper = getattr(entry, "__mapper__", None)
            if mapper is None:
                continue
            try:
                props = list(mapper.iterate_properties)
            except Exception:
                continue
            for prop in props:
                if (
                    isinstance(prop, RelationshipProperty)
                    and isinstance(prop.argument, str)
                ):
                    name = prop.argument.rsplit(".", 1)[-1]
                    if name not in known:
                        needed.add(name)
        existing_tables = set(Base.metadata.tables.keys())
        for name in sorted(needed):
            if name in registry._class_registry:
                continue
            snake = _camel_to_snake(name)
            if snake in existing_tables:
                tablename, extend = snake, True
            elif snake + "s" in existing_tables:
                tablename, extend = snake + "s", True
            else:
                tablename = f"_test_stub_class_{name.lower()}"
                extend = tablename in existing_tables
            attrs: dict = {
                "__tablename__": tablename,
                "__table_args__": {"extend_existing": True} if extend else {},
            }
            if not extend:
                attrs["id"] = Column(Integer, primary_key=True)
            type(name, (Base,), attrs)

    def _clear_failed_mapper_caches() -> None:
        from sqlalchemy.orm import configure_mappers
        registry = Base.registry
        for entry in list(registry._class_registry.values()):
            mapper = getattr(entry, "__mapper__", None)
            if mapper is None:
                continue
            if getattr(mapper, "_configure_failed", False):
                mapper._configure_failed = False
            if getattr(mapper, "configured", False):
                mapper.configured = False
        try:
            configure_mappers()
        except Exception:
            pass

    _stub_unresolved_fk_targets()
    _stub_unresolved_relationship_targets()
    _clear_failed_mapper_caches()


# Imports needed by tests — these only resolve when the harness above
# has run (gate is on). Behind a runtime guard so the
# pre-skip-collection phase doesn't fail.
if os.environ.get("TMS_RUN_INTEGRATION_TESTS") == "1":
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from azirella_data_model.master import (
        OutboundOrderLine,
        TransportationLane,
    )
    from azirella_data_model.transport_plan import (
        ProductLane,
        ProductLaneSource,
    )

    @pytest.fixture
    def substrate_db():
        """In-memory SQLite session with all substrate tables created."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = Session(engine)
        try:
            yield session
        finally:
            session.close()


_AGGREGATOR_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "app", "services", "powell", "product_lane_aggregator.py",
)


def _load_aggregator_module():
    spec = importlib.util.spec_from_file_location(
        "product_lane_aggregator_integration_test", _AGGREGATOR_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


aggregator_module = _load_aggregator_module()
ProductLaneAggregator = aggregator_module.ProductLaneAggregator


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _seed_lane(db, *, lane_id: int, from_site: str, to_site: str,
               config_id: int = 1) -> None:
    db.add(
        TransportationLane(
            id=lane_id,
            from_site_id=from_site,
            to_site_id=to_site,
            config_id=config_id,
        )
    )
    db.flush()


def _seed_line(
    db, *,
    order_id: int,
    line_number: int,
    product_id: str,
    site_id: str,
    market_demand_site_id: str,
    shipped_quantity: float,
    first_ship_date: date,
    config_id: int = 1,
) -> None:
    db.add(
        OutboundOrderLine(
            order_id=order_id,
            line_number=line_number,
            product_id=product_id,
            site_id=site_id,
            market_demand_site_id=market_demand_site_id,
            shipped_quantity=shipped_quantity,
            ordered_quantity=shipped_quantity,
            first_ship_date=first_ship_date,
            order_date=first_ship_date,
            requested_delivery_date=first_ship_date,
            config_id=config_id,
        )
    )
    db.flush()


# ---------------------------------------------------------------------------
# Single-product / single-lane — share = 1.0
# ---------------------------------------------------------------------------


def test_single_product_single_lane_persists_share_one(substrate_db):
    db = substrate_db
    _seed_lane(db, lane_id=10, from_site="DC-1", to_site="CUST-A")
    ps, pe = date(2026, 5, 4), date(2026, 5, 11)
    _seed_line(
        db, order_id=1, line_number=1,
        product_id="SKU-A", site_id="DC-1",
        market_demand_site_id="CUST-A",
        shipped_quantity=100.0, first_ship_date=date(2026, 5, 6),
    )

    agg = ProductLaneAggregator()
    result = agg.aggregate_period(
        db, tenant_id=42, config_id=1,
        period_start=ps, period_end=pe,
    )

    assert result.rows_written == 1
    assert result.lanes_affected == 1
    assert result.total_volume == 100.0

    rows = db.query(ProductLane).all()
    assert len(rows) == 1
    assert rows[0].lane_id == 10
    assert rows[0].product_id == "SKU-A"
    assert rows[0].volume_units == 100.0
    assert rows[0].volume_share == 1.0
    assert rows[0].source == ProductLaneSource.OBSERVED_HISTORY


# ---------------------------------------------------------------------------
# Two products on one lane — shares sum to 1.0
# ---------------------------------------------------------------------------


def test_multi_product_share_sums_to_one_via_db(substrate_db):
    db = substrate_db
    _seed_lane(db, lane_id=10, from_site="DC-1", to_site="CUST-A")
    ps, pe = date(2026, 5, 4), date(2026, 5, 11)
    _seed_line(
        db, order_id=1, line_number=1,
        product_id="SKU-A", site_id="DC-1",
        market_demand_site_id="CUST-A",
        shipped_quantity=70.0, first_ship_date=date(2026, 5, 5),
    )
    _seed_line(
        db, order_id=1, line_number=2,
        product_id="SKU-B", site_id="DC-1",
        market_demand_site_id="CUST-A",
        shipped_quantity=30.0, first_ship_date=date(2026, 5, 7),
    )

    agg = ProductLaneAggregator()
    result = agg.aggregate_period(
        db, tenant_id=42, config_id=1,
        period_start=ps, period_end=pe,
    )

    assert result.rows_written == 2
    rows = {r.product_id: r for r in db.query(ProductLane).all()}
    assert rows["SKU-A"].volume_share == pytest.approx(0.7)
    assert rows["SKU-B"].volume_share == pytest.approx(0.3)
    assert (
        rows["SKU-A"].volume_share + rows["SKU-B"].volume_share == 1.0
    )


# ---------------------------------------------------------------------------
# Period filter — out-of-window shipments excluded
# ---------------------------------------------------------------------------


def test_period_filter_excludes_out_of_window(substrate_db):
    db = substrate_db
    _seed_lane(db, lane_id=10, from_site="DC-1", to_site="CUST-A")
    ps, pe = date(2026, 5, 4), date(2026, 5, 11)
    # In-window
    _seed_line(
        db, order_id=1, line_number=1,
        product_id="SKU-A", site_id="DC-1",
        market_demand_site_id="CUST-A",
        shipped_quantity=100.0, first_ship_date=date(2026, 5, 7),
    )
    # Before window
    _seed_line(
        db, order_id=2, line_number=1,
        product_id="SKU-A", site_id="DC-1",
        market_demand_site_id="CUST-A",
        shipped_quantity=999.0, first_ship_date=date(2026, 5, 3),
    )
    # On the period_end boundary (exclusive)
    _seed_line(
        db, order_id=3, line_number=1,
        product_id="SKU-A", site_id="DC-1",
        market_demand_site_id="CUST-A",
        shipped_quantity=999.0, first_ship_date=date(2026, 5, 11),
    )

    agg = ProductLaneAggregator()
    result = agg.aggregate_period(
        db, tenant_id=42, config_id=1,
        period_start=ps, period_end=pe,
    )
    assert result.total_volume == 100.0


# ---------------------------------------------------------------------------
# Zero-quantity shipments excluded
# ---------------------------------------------------------------------------


def test_zero_shipped_quantity_excluded_via_db(substrate_db):
    db = substrate_db
    _seed_lane(db, lane_id=10, from_site="DC-1", to_site="CUST-A")
    ps, pe = date(2026, 5, 4), date(2026, 5, 11)
    _seed_line(
        db, order_id=1, line_number=1,
        product_id="SKU-A", site_id="DC-1",
        market_demand_site_id="CUST-A",
        shipped_quantity=0.0, first_ship_date=date(2026, 5, 5),
    )
    _seed_line(
        db, order_id=2, line_number=1,
        product_id="SKU-B", site_id="DC-1",
        market_demand_site_id="CUST-A",
        shipped_quantity=50.0, first_ship_date=date(2026, 5, 5),
    )

    agg = ProductLaneAggregator()
    result = agg.aggregate_period(
        db, tenant_id=42, config_id=1,
        period_start=ps, period_end=pe,
    )

    assert result.rows_written == 1
    assert result.total_volume == 50.0


# ---------------------------------------------------------------------------
# Empty period
# ---------------------------------------------------------------------------


def test_empty_period_returns_zero_rows_via_db(substrate_db):
    db = substrate_db
    _seed_lane(db, lane_id=10, from_site="DC-1", to_site="CUST-A")
    ps, pe = date(2026, 5, 4), date(2026, 5, 11)
    # No outbound_order_line rows seeded.

    agg = ProductLaneAggregator()
    result = agg.aggregate_period(
        db, tenant_id=42, config_id=1,
        period_start=ps, period_end=pe,
    )
    assert result.rows_written == 0
    assert result.total_volume == 0.0
    assert db.query(ProductLane).count() == 0


# ---------------------------------------------------------------------------
# Upsert — re-running the same period replaces, doesn't duplicate
# ---------------------------------------------------------------------------


def test_upsert_replaces_existing_observed_row_via_db(substrate_db):
    db = substrate_db
    _seed_lane(db, lane_id=10, from_site="DC-1", to_site="CUST-A")
    ps, pe = date(2026, 5, 4), date(2026, 5, 11)
    _seed_line(
        db, order_id=1, line_number=1,
        product_id="SKU-A", site_id="DC-1",
        market_demand_site_id="CUST-A",
        shipped_quantity=100.0, first_ship_date=date(2026, 5, 5),
    )

    agg = ProductLaneAggregator()
    agg.aggregate_period(
        db, tenant_id=42, config_id=1,
        period_start=ps, period_end=pe,
    )

    # Add late-arriving correction (return / billing adj) and re-run.
    _seed_line(
        db, order_id=2, line_number=1,
        product_id="SKU-A", site_id="DC-1",
        market_demand_site_id="CUST-A",
        shipped_quantity=20.0, first_ship_date=date(2026, 5, 6),
    )
    agg.aggregate_period(
        db, tenant_id=42, config_id=1,
        period_start=ps, period_end=pe,
    )

    rows = (
        db.query(ProductLane)
        .filter(ProductLane.source == ProductLaneSource.OBSERVED_HISTORY)
        .all()
    )
    # Single OBSERVED row for the (lane, product, period) tuple, with
    # the corrected total — no duplicates from the re-run.
    assert len(rows) == 1
    assert rows[0].volume_units == 120.0


# ---------------------------------------------------------------------------
# Source-extended uniqueness — observed upsert leaves forecast rows alone
# ---------------------------------------------------------------------------


def test_upsert_does_not_touch_forecast_aggregated_rows_via_db(substrate_db):
    db = substrate_db
    _seed_lane(db, lane_id=10, from_site="DC-1", to_site="CUST-A")
    ps, pe = date(2026, 5, 4), date(2026, 5, 11)
    _seed_line(
        db, order_id=1, line_number=1,
        product_id="SKU-A", site_id="DC-1",
        market_demand_site_id="CUST-A",
        shipped_quantity=100.0, first_ship_date=date(2026, 5, 5),
    )

    # Pre-seed a forecast row.
    db.add(
        ProductLane(
            tenant_id=42, lane_id=10, product_id="SKU-A",
            period_start=ps, period_end=pe,
            volume_units=80.0, volume_share=0.5,
            source=ProductLaneSource.FORECAST_AGGREGATED,
            confidence=0.6,
        )
    )
    db.flush()

    agg = ProductLaneAggregator()
    agg.aggregate_period(
        db, tenant_id=42, config_id=1,
        period_start=ps, period_end=pe,
    )

    # Both rows present — observed (just written) + forecast (untouched).
    rows = db.query(ProductLane).all()
    assert len(rows) == 2
    by_source = {r.source: r for r in rows}
    assert by_source[ProductLaneSource.OBSERVED_HISTORY].volume_units == 100.0
    assert by_source[ProductLaneSource.FORECAST_AGGREGATED].volume_units == 80.0
    assert by_source[ProductLaneSource.FORECAST_AGGREGATED].confidence == 0.6


# ---------------------------------------------------------------------------
# config_id scoping
# ---------------------------------------------------------------------------


def test_config_id_scopes_aggregation_via_db(substrate_db):
    db = substrate_db
    _seed_lane(db, lane_id=10, from_site="DC-1", to_site="CUST-A", config_id=1)
    _seed_lane(db, lane_id=20, from_site="DC-1", to_site="CUST-A", config_id=2)
    ps, pe = date(2026, 5, 4), date(2026, 5, 11)
    _seed_line(
        db, order_id=1, line_number=1,
        product_id="SKU-A", site_id="DC-1",
        market_demand_site_id="CUST-A",
        shipped_quantity=100.0, first_ship_date=date(2026, 5, 5),
        config_id=1,
    )
    _seed_line(
        db, order_id=2, line_number=1,
        product_id="SKU-A", site_id="DC-1",
        market_demand_site_id="CUST-A",
        shipped_quantity=999.0, first_ship_date=date(2026, 5, 5),
        config_id=2,  # different config — excluded
    )

    agg = ProductLaneAggregator()
    result = agg.aggregate_period(
        db, tenant_id=42, config_id=1,
        period_start=ps, period_end=pe,
    )
    assert result.total_volume == 100.0


# ---------------------------------------------------------------------------
# JOIN correctness — orders without a matching lane are excluded
# ---------------------------------------------------------------------------


def test_orders_without_matching_lane_excluded(substrate_db):
    """Orders shipped between sites with no transportation_lane row
    are excluded by the inner JOIN. Important: the aggregator does
    not silently invent lanes."""
    db = substrate_db
    # Lane DC-1 → CUST-A only.
    _seed_lane(db, lane_id=10, from_site="DC-1", to_site="CUST-A")
    ps, pe = date(2026, 5, 4), date(2026, 5, 11)
    # Shipment via DC-1 → CUST-A (matched)
    _seed_line(
        db, order_id=1, line_number=1,
        product_id="SKU-A", site_id="DC-1",
        market_demand_site_id="CUST-A",
        shipped_quantity=100.0, first_ship_date=date(2026, 5, 5),
    )
    # Shipment via DC-2 → CUST-B (no lane — excluded)
    _seed_line(
        db, order_id=2, line_number=1,
        product_id="SKU-A", site_id="DC-2",
        market_demand_site_id="CUST-B",
        shipped_quantity=999.0, first_ship_date=date(2026, 5, 5),
    )

    agg = ProductLaneAggregator()
    result = agg.aggregate_period(
        db, tenant_id=42, config_id=1,
        period_start=ps, period_end=pe,
    )
    assert result.rows_written == 1
    assert result.total_volume == 100.0
