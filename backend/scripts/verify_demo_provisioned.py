#!/usr/bin/env python3
"""Post-seed sanity check for Food Dist demo tenant.

Mechanical row-count verification — confirms the seed produced
roughly the volumes the generator advertises (1095-day default since
PR #3). Not a behavioural test (those belong in the integration
suite); this catches regressions in the generator or partial seed
runs.

Usage:
    docker compose exec backend python scripts/verify_demo_provisioned.py
    docker compose exec backend python scripts/verify_demo_provisioned.py --tenant food_dist

Exit code:
    0 — every check passed.
    1 — at least one check failed.

The expected ranges are calibrated to the current generator parameters
(``FoodDistHistoryGenerator`` default ``days=1095``). If the generator
moves, update the ranges here in lockstep.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import or_, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import sync_engine
from app.models.tenant import Tenant


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class Check:
    name: str
    actual: int
    min_expected: int
    max_expected: int
    notes: str = ""

    @property
    def status(self) -> str:
        if self.actual == 0 and self.min_expected > 0:
            return "FAIL"
        if self.min_expected <= self.actual <= self.max_expected:
            return "PASS"
        if self.actual < self.min_expected:
            return "WARN-LOW"
        return "WARN-HIGH"

    def render(self) -> str:
        marker = {
            "PASS": "✓",
            "FAIL": "✗",
            "WARN-LOW": "△",
            "WARN-HIGH": "△",
        }[self.status]
        range_str = f"[{self.min_expected:,}–{self.max_expected:,}]"
        line = (
            f"  {marker} {self.status:9}  {self.name:<32}  "
            f"actual={self.actual:>10,}   expected {range_str}"
        )
        if self.notes:
            line += f"   ({self.notes})"
        return line


@dataclass
class TenantReport:
    tenant_label: str
    tenant_name: Optional[str]
    tenant_id: Optional[int]
    checks: List[Check] = field(default_factory=list)
    skipped_reason: Optional[str] = None

    @property
    def all_pass(self) -> bool:
        if self.skipped_reason is not None:
            return False
        return all(c.status == "PASS" for c in self.checks)

    @property
    def failure_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "FAIL")

    def render(self) -> str:
        lines = [f"\n=== {self.tenant_label} ==="]
        if self.skipped_reason is not None:
            lines.append(f"  SKIPPED — {self.skipped_reason}")
            return "\n".join(lines)
        lines.append(
            f"  Tenant: {self.tenant_name} (id={self.tenant_id})"
        )
        for c in self.checks:
            lines.append(c.render())
        passed = sum(1 for c in self.checks if c.status == "PASS")
        warns = sum(1 for c in self.checks if c.status.startswith("WARN"))
        fails = self.failure_count
        lines.append(
            f"\n  Summary: {passed}/{len(self.checks)} pass, "
            f"{warns} warn, {fails} fail"
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-table count helper
# ---------------------------------------------------------------------------


def _count(db: Session, table: str, where: str, params: dict) -> int:
    """Count rows in ``table`` matching ``where``. Returns 0 if the
    table doesn't exist or the query fails — the caller decides via
    expected-range whether 0 is fatal."""
    try:
        return int(
            db.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE {where}"),
                params,
            ).scalar() or 0
        )
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Food Dist
# ---------------------------------------------------------------------------


def verify_food_dist(db: Session) -> TenantReport:
    """Sanity-check the Food Dist demo tenant.

    Calibrated to the 1095-day (3-year) generator shipped in PR #3.
    Volume estimates (per FoodDistHistoryGenerator):

      - 13 customers × weekly orders × 156 weeks ≈ 2K outbound orders
      - 6 suppliers × weekly POs × 156 weeks ≈ 1K inbound orders
      - daily inv_level snapshots × ~75 site-product combos ≈ 55K rows
      - shipments per outbound + per inbound + per transfer ≈ 4-6K
    """
    report = TenantReport(tenant_label="Food Dist", tenant_name=None, tenant_id=None)
    tenant = (
        db.query(Tenant)
        .filter(
            or_(
                Tenant.name == "Food Dist",
                Tenant.name.ilike("Food Dist%"),
                Tenant.name.ilike("%Food%Dist%"),
                Tenant.slug == "food-dist",
            )
        )
        .first()
    )
    if tenant is None:
        report.skipped_reason = (
            "Tenant 'Food Dist' not found. Run `make seed-food-dist-reset` first."
        )
        return report
    report.tenant_name = tenant.name
    report.tenant_id = tenant.id

    config_id_subq = "(SELECT id FROM supply_chain_configs WHERE tenant_id = :tid)"
    by_config = f"config_id IN {config_id_subq}"
    params = {"tid": tenant.id}

    # ----- Master data -----
    config_count = _count(db, "supply_chain_configs", "tenant_id = :tid", params)
    report.checks.append(Check(
        "supply_chain_configs", config_count, 1, 5,
        notes="typically one canonical config",
    ))

    site_count = _count(db, "site", by_config, params)
    # 1 CDC + 3 RDCs + 13 customer ship-tos + 6 supplier ship-froms + carriers
    report.checks.append(Check(
        "sites (CDC + RDCs + partners)", site_count, 4, 60,
    ))

    product_count = _count(db, "product", by_config, params)
    # 25 products: 6 frozen protein + 5 dairy + 5 dry pantry + 5 frozen
    # dessert + 4 beverage = 25 base, plus a few launches ≈ 25-30.
    report.checks.append(Check(
        "products", product_count, 20, 60,
    ))

    # ----- Demand-side history (3-year shape) -----
    outbound_orders = _count(db, "outbound_order", by_config, params)
    report.checks.append(Check(
        "outbound_order (3y demand)", outbound_orders, 1_000, 4_000,
        notes="~2K expected (13 cust × ~52 wks × 3 yrs)",
    ))

    outbound_lines = _count(db, "outbound_order_line", by_config, params)
    report.checks.append(Check(
        "outbound_order_line", outbound_lines, 5_000, 25_000,
    ))

    inbound_orders = _count(db, "inbound_order", by_config, params)
    report.checks.append(Check(
        "inbound_order (supplier POs)", inbound_orders, 500, 2_500,
        notes="~1K expected (6 sup × ~52 × 3y)",
    ))

    forecasts = _count(db, "forecast", by_config, params)
    report.checks.append(Check(
        "forecast", forecasts, 2_000, 30_000,
    ))

    inv_levels = _count(db, "inv_level", by_config, params)
    report.checks.append(Check(
        "inv_level (daily snapshots)", inv_levels, 30_000, 100_000,
        notes="~55K expected (75 site-product × 1095 days)",
    ))

    # ----- Shipment + lot tracking (Food Dist-specific) -----
    shipments = _count(db, "shipment", by_config, params)
    report.checks.append(Check(
        "shipment (with lot traceability)", shipments, 3_000, 15_000,
    ))

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

VERIFIERS = {
    "food_dist": verify_food_dist,
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Post-seed sanity check for Food Dist demo tenant.",
    )
    p.add_argument(
        "--tenant",
        choices=list(VERIFIERS.keys()) + ["all"],
        default="all",
        help="Which demo tenant to verify (default: all).",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)
    db: Session = SessionLocal()

    selected = list(VERIFIERS.keys()) if args.tenant == "all" else [args.tenant]
    reports: List[TenantReport] = []
    try:
        for key in selected:
            reports.append(VERIFIERS[key](db))
    finally:
        db.close()

    print("=" * 72)
    print("Demo provisioning sanity check")
    print("=" * 72)
    for r in reports:
        print(r.render())

    print("\n" + "=" * 72)
    failed_tenants = [r for r in reports if not r.all_pass]
    if not failed_tenants:
        print(f"All {len(reports)} tenant(s) PASSED.")
        return 0
    print(f"{len(failed_tenants)}/{len(reports)} tenant(s) had issues:")
    for r in failed_tenants:
        if r.skipped_reason is not None:
            print(f"  - {r.tenant_label}: SKIPPED ({r.skipped_reason})")
        else:
            print(f"  - {r.tenant_label}: {r.failure_count} FAIL check(s)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
