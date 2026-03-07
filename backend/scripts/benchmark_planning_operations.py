#!/usr/bin/env python3
"""
Planning Operations Benchmark -- profiles planning services at various network
sizes to identify bottlenecks.

Usage (inside Docker container):
    python scripts/benchmark_planning_operations.py --sizes 50,200,500
    python scripts/benchmark_planning_operations.py --sizes 100 --db-url postgresql://u:p@h/db
"""
import argparse, asyncio, os, random, sys, time, uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

_script_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.dirname(_script_dir)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.models.base import Base
from app.models.supply_chain_config import SupplyChainConfig, Site, TransportationLane
from app.models.sc_entities import (
    Forecast, InvLevel, InvPolicy, OutboundOrderLine,
    Product, ProductBom, SourcingRules,
)


class QueryProfiler:
    """Counts SQL queries and cumulative execution time via engine events."""

    def __init__(self, engine):
        self._engine = engine
        self.query_count = 0
        self.total_db_time = 0.0
        self._pending: Dict[int, float] = {}

    def _before(self, conn, cursor, stmt, params, ctx, many):
        self._pending[id(cursor)] = time.perf_counter()

    def _after(self, conn, cursor, stmt, params, ctx, many):
        start = self._pending.pop(id(cursor), None)
        if start is not None:
            self.total_db_time += time.perf_counter() - start
        self.query_count += 1

    def attach(self):
        event.listen(self._engine, "before_cursor_execute", self._before)
        event.listen(self._engine, "after_cursor_execute", self._after)

    def reset(self):
        self.query_count = 0
        self.total_db_time = 0.0
        self._pending.clear()

    @contextmanager
    def profile(self):
        self.reset()
        yield self


class BenchmarkResult:
    __slots__ = ("network_size", "operation", "wall_time", "db_queries",
                 "db_time", "extra")

    def __init__(self, network_size, operation, wall_time, db_queries,
                 db_time, extra=None):
        self.network_size = network_size
        self.operation = operation
        self.wall_time = wall_time
        self.db_queries = db_queries
        self.db_time = db_time
        self.extra = extra or {}


class PlanningBenchmark:
    """Creates synthetic supply-chain networks and benchmarks planning services."""

    LAYER_RATIOS = {
        "supplier":     (0.15, "market_supply", "MARKET_SUPPLY"),
        "manufacturer": (0.15, "manufacturer",  "MANUFACTURER"),
        "dc":           (0.25, "inventory",     "DISTRIBUTOR"),
        "retailer":     (0.30, "inventory",     "RETAILER"),
        "customer":     (0.15, "market_demand", "MARKET_DEMAND"),
    }

    def __init__(self, db_url: str):
        self._engine = create_engine(db_url, echo=False, pool_pre_ping=True)
        self._SF = sessionmaker(bind=self._engine, expire_on_commit=False)
        self._profiler = QueryProfiler(self._engine)
        self._profiler.attach()
        self.results: List[BenchmarkResult] = []

    def setup_synthetic_network(self, num_sites: int) -> int:
        """Create layered config: suppliers->manufacturers->DCs->retailers->customers."""
        db: Session = self._SF()
        try:
            tag = uuid.uuid4().hex[:8]
            row = db.execute(text("SELECT id FROM customers LIMIT 1")).fetchone()
            if row is None:
                raise RuntimeError("No customers in DB. Run 'make db-bootstrap' first.")
            customer_id = row[0]

            config = SupplyChainConfig(
                name=f"Bench-{num_sites}-{tag}", description="Benchmark network",
                customer_id=customer_id, is_active=False, scenario_type="SIMULATION")
            db.add(config); db.flush()
            config_id = config.id

            layer_sites: Dict[str, List[Site]] = defaultdict(list)
            remaining = num_sites
            layers = list(self.LAYER_RATIOS.keys())
            for idx, layer in enumerate(layers):
                ratio, master_type, site_type = self.LAYER_RATIOS[layer]
                count = remaining if idx == len(layers) - 1 else max(1, int(num_sites * ratio))
                if idx < len(layers) - 1:
                    remaining -= count
                for i in range(count):
                    s = Site(config_id=config_id, name=f"{layer}_{i}_{tag}",
                             type=site_type, master_type=master_type)
                    db.add(s); layer_sites[layer].append(s)
            db.flush()

            ordered = ["supplier", "manufacturer", "dc", "retailer", "customer"]
            for up_l, dn_l in zip(ordered[:-1], ordered[1:]):
                for ds in layer_sites[dn_l]:
                    n = min(len(layer_sites[up_l]), random.randint(1, 3))
                    for us in random.sample(layer_sites[up_l], n):
                        db.add(TransportationLane(config_id=config_id,
                               from_site_id=us.id, to_site_id=ds.id,
                               capacity=random.randint(100, 1000)))

            num_products = max(2, num_sites // 5)
            products: List[Product] = []
            for i in range(num_products):
                p = Product(id=f"BENCH-{tag}-P{i:04d}", description=f"Bench product {i}",
                            config_id=config_id, unit_cost=round(random.uniform(5, 200), 2),
                            is_active="true")
                db.add(p); products.append(p)
            db.flush()

            if len(products) >= 2:
                db.add(ProductBom(product_id=products[0].id,
                       component_product_id=products[1].id,
                       component_quantity=2.0, config_id=config_id, is_active="true"))

            planning_sites = layer_sites["dc"] + layer_sites["retailer"]
            start = date.today()
            for product in products:
                for site in planning_sites:
                    for d in range(30):
                        qty = round(random.uniform(10, 500), 1)
                        db.add(Forecast(product_id=product.id, site_id=site.id,
                               forecast_date=start + timedelta(days=d),
                               forecast_p50=qty, forecast_quantity=qty,
                               config_id=config_id))
                    for j in range(10):
                        db.add(OutboundOrderLine(
                            order_id=f"ORD-{tag}-{product.id}-{site.id}-{j}",
                            line_number=1, product_id=product.id, site_id=site.id,
                            ordered_quantity=round(random.uniform(5, 200), 1),
                            requested_delivery_date=start + timedelta(days=random.randint(0, 29)),
                            config_id=config_id))
                    db.add(InvPolicy(product_id=product.id, site_id=site.id,
                           ss_policy="sl", service_level=0.95,
                           config_id=config_id, is_active="true"))
                    db.add(InvLevel(product_id=product.id, site_id=site.id,
                           on_hand_qty=round(random.uniform(50, 500), 1),
                           config_id=config_id))
                if layer_sites["supplier"]:
                    db.add(SourcingRules(
                        id=f"SR-{tag}-{product.id}", product_id=product.id,
                        from_site_id=random.choice(layer_sites["supplier"]).id,
                        to_site_id=random.choice(planning_sites).id,
                        sourcing_rule_type="buy", sourcing_priority=1,
                        config_id=config_id, is_active="true"))

            db.commit()
            n_ps = len(planning_sites)
            print(f"  [setup] config {config_id}: {num_sites} sites, "
                  f"{num_products} products, {num_products * n_ps * 30} forecasts, "
                  f"{num_products * n_ps * 10} orders")
            return config_id
        except Exception:
            db.rollback(); raise
        finally:
            db.close()

    def _meta(self, config_id: int) -> Tuple[int, int]:
        db = self._SF()
        try:
            return db.get(SupplyChainConfig, config_id).customer_id, 30
        finally:
            db.close()

    def benchmark_demand_processing(self, config_id: int, num_sites: int):
        from app.services.sc_planning.demand_processor import DemandProcessor
        gid, hz = self._meta(config_id)
        proc = DemandProcessor(config_id, gid)
        with self._profiler.profile() as prof:
            t0 = time.perf_counter()
            res = asyncio.get_event_loop().run_until_complete(
                proc.process_demand(date.today(), hz))
            wall = time.perf_counter() - t0
        self.results.append(BenchmarkResult(num_sites, "Demand Processing",
                            wall, prof.query_count, prof.total_db_time,
                            {"demand_entries": len(res)}))

    def benchmark_inventory_targets(self, config_id: int, num_sites: int):
        from app.services.sc_planning.demand_processor import DemandProcessor
        from app.services.sc_planning.inventory_target_calculator import InventoryTargetCalculator
        gid, hz = self._meta(config_id)
        loop = asyncio.get_event_loop()
        nd = loop.run_until_complete(DemandProcessor(config_id, gid).process_demand(date.today(), hz))
        calc = InventoryTargetCalculator(config_id, gid)
        self._profiler.reset()
        with self._profiler.profile() as prof:
            t0 = time.perf_counter()
            tgt = loop.run_until_complete(calc.calculate_targets(nd, date.today()))
            wall = time.perf_counter() - t0
        self.results.append(BenchmarkResult(num_sites, "Inventory Targets",
                            wall, prof.query_count, prof.total_db_time,
                            {"target_entries": len(tgt)}))

    def benchmark_net_requirements(self, config_id: int, num_sites: int):
        from app.services.sc_planning.demand_processor import DemandProcessor
        from app.services.sc_planning.inventory_target_calculator import InventoryTargetCalculator
        from app.services.sc_planning.net_requirements_calculator import NetRequirementsCalculator
        gid, hz = self._meta(config_id)
        loop = asyncio.get_event_loop()
        nd = loop.run_until_complete(DemandProcessor(config_id, gid).process_demand(date.today(), hz))
        tgt = loop.run_until_complete(InventoryTargetCalculator(config_id, gid).calculate_targets(nd, date.today()))
        nrc = NetRequirementsCalculator(config_id, gid, hz)
        self._profiler.reset()
        with self._profiler.profile() as prof:
            t0 = time.perf_counter()
            plans = loop.run_until_complete(nrc.calculate_requirements(nd, tgt, date.today()))
            wall = time.perf_counter() - t0
        self.results.append(BenchmarkResult(num_sites, "Net Requirements",
                            wall, prof.query_count, prof.total_db_time,
                            {"supply_plans": len(plans)}))

    def benchmark_exception_detection(self, config_id: int, num_sites: int):
        from app.services.forecast_exception_detector import ForecastExceptionDetector
        db: Session = self._SF()
        try:
            det = ForecastExceptionDetector(db)
            ps, pe = date.today(), date.today() + timedelta(days=30)
            self._profiler.reset()
            with self._profiler.profile() as prof:
                t0 = time.perf_counter()
                res = det.run_detection(config_id=config_id, period_start=ps,
                                        period_end=pe, threshold_percent=20.0)
                wall = time.perf_counter() - t0
            self.results.append(BenchmarkResult(num_sites, "Exception Detection",
                                wall, prof.query_count, prof.total_db_time,
                                {"analyzed": res.get("products_analyzed", 0),
                                 "exceptions": res.get("exceptions_created", 0)}))
        finally:
            db.close()

    def cleanup(self, config_id: int):
        db: Session = self._SF()
        try:
            for m in (Forecast, OutboundOrderLine, InvPolicy, InvLevel,
                      SourcingRules, ProductBom):
                db.query(m).filter(m.config_id == config_id).delete(synchronize_session=False)
            db.query(Product).filter(Product.config_id == config_id).delete(synchronize_session=False)
            db.query(TransportationLane).filter(TransportationLane.config_id == config_id).delete(synchronize_session=False)
            db.query(Site).filter(Site.config_id == config_id).delete(synchronize_session=False)
            db.query(SupplyChainConfig).filter(SupplyChainConfig.id == config_id).delete(synchronize_session=False)
            db.commit()
            print(f"  [cleanup] Removed config {config_id}")
        except Exception:
            db.rollback(); raise
        finally:
            db.close()

    def run_suite(self, sizes: List[int]):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        for n in sizes:
            print(f"\n{'=' * 70}\n  Network Size: {n} sites\n{'=' * 70}")
            cid = self.setup_synthetic_network(n)
            ops = [
                ("Demand Processing",   self.benchmark_demand_processing),
                ("Inventory Targets",   self.benchmark_inventory_targets),
                ("Net Requirements",    self.benchmark_net_requirements),
                ("Exception Detection", self.benchmark_exception_detection),
            ]
            for name, fn in ops:
                print(f"  Running: {name} ...", end=" ", flush=True)
                try:
                    fn(cid, n)
                    r = self.results[-1]
                    print(f"done  ({r.wall_time:.3f}s, {r.db_queries} queries, {r.db_time:.3f}s DB)")
                except Exception as exc:
                    print(f"FAILED: {exc}")
                    self.results.append(BenchmarkResult(n, name, -1, -1, -1, {"error": str(exc)}))
            self.cleanup(cid)
        loop.close()

    def print_report(self):
        if not self.results:
            print("No results."); return

        hdr = (f"| {'Network Size':>13} | {'Operation':<22} | {'Wall Time (s)':>14} "
               f"| {'DB Queries':>11} | {'DB Time (s)':>12} | {'Extra':<30} |")
        sep = "|" + "-" * 15 + "|" + "-" * 24 + "|" + "-" * 16 + "|" + "-" * 13 + "|" + "-" * 14 + "|" + "-" * 32 + "|"

        print(f"\n{'=' * len(hdr)}")
        print("  PLANNING OPERATIONS BENCHMARK REPORT")
        print(f"{'=' * len(hdr)}")
        print(hdr); print(sep)

        for r in self.results:
            extra = ""
            if "error" in r.extra:
                extra = f"ERROR: {r.extra['error'][:28]}"
            elif r.extra:
                extra = ", ".join(f"{k}={v}" for k, v in r.extra.items())
            w = f"{r.wall_time:.4f}" if r.wall_time >= 0 else "FAIL"
            q = str(r.db_queries) if r.db_queries >= 0 else "FAIL"
            d = f"{r.db_time:.4f}" if r.db_time >= 0 else "FAIL"
            print(f"| {str(r.network_size) + ' sites':>13} | {r.operation:<22} "
                  f"| {w:>14} | {q:>11} | {d:>12} | {extra:<30} |")

        print(sep)
        totals: Dict[int, Dict[str, float]] = defaultdict(lambda: {"w": 0.0, "q": 0, "d": 0.0})
        for r in self.results:
            if r.wall_time >= 0:
                totals[r.network_size]["w"] += r.wall_time
                totals[r.network_size]["q"] += r.db_queries
                totals[r.network_size]["d"] += r.db_time
        print(f"\n  TOTALS BY NETWORK SIZE")
        print(f"| {'Size':>13} | {'Total Wall (s)':>14} | {'Total Queries':>14} | {'Total DB (s)':>14} |")
        print("|" + "-" * 15 + "|" + "-" * 16 + "|" + "-" * 16 + "|" + "-" * 16 + "|")
        for sz in sorted(totals):
            t = totals[sz]
            print(f"| {str(sz) + ' sites':>13} | {t['w']:>14.4f} | {int(t['q']):>14} | {t['d']:>14.4f} |")
        print()


def _resolve_db_url(cli_url: Optional[str]) -> str:
    if cli_url:
        return cli_url
    for key in ("SQLALCHEMY_DATABASE_URI", "DATABASE_URL"):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    h = os.environ.get("POSTGRESQL_HOST", "db")
    pt = os.environ.get("POSTGRESQL_PORT", "5432")
    u = os.environ.get("POSTGRESQL_USER", "autonomy_user")
    pw = os.environ.get("POSTGRESQL_PASSWORD", "autonomy_password")
    db = os.environ.get("POSTGRESQL_DATABASE", "autonomy")
    return f"postgresql://{u}:{pw}@{h}:{pt}/{db}"


def main():
    parser = argparse.ArgumentParser(description="Benchmark planning operations")
    parser.add_argument("--sizes", type=str, default="50,200,500",
                        help="Comma-separated network sizes (default: 50,200,500)")
    parser.add_argument("--db-url", type=str, default=None,
                        help="SQLAlchemy DB URL (auto-detected from env if omitted)")
    args = parser.parse_args()

    sizes = [int(s.strip()) for s in args.sizes.split(",")]
    db_url = _resolve_db_url(args.db_url)
    masked = db_url.split("@")[-1] if "@" in db_url else db_url
    print(f"Database: ...@{masked}")
    print(f"Network sizes: {sizes}")

    bench = PlanningBenchmark(db_url)
    bench.run_suite(sizes)
    bench.print_report()


if __name__ == "__main__":
    main()
