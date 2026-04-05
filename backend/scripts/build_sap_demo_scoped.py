#!/usr/bin/env python3
"""Build a scoped SAP Demo config from CSV files.

Scope = Sales BOM tops (STLAN 3/5) ∪ Spare parts (MTART=ERSA) ∪ Configurables
(MTART=KMAT) ∪ recursive BOM explosion through all children.

The original CSV files are NOT modified. They are read into DataFrames,
filtered in memory, and passed to the SAPConfigBuilder. Only the resulting
config + child entities are written to the database.

Usage:
    python scripts/build_sap_demo_scoped.py

Prerequisites:
    - CSV files at imports/SAP_Demo/*.csv (read-only)
    - tenant 20 (Autonomy SAP Demo) exists
    - All old SAP Demo configs (tenant 20) deleted before running

See docs/internal/VIRTUAL_CLOCK_ARCHITECTURE.md for related work.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Set, List, Optional

# Ensure backend app is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
)
logger = logging.getLogger("build_sap_demo_scoped")


# Core SAP tables the builder expects. If a file is missing, it's optional.
SAP_TABLES = [
    "T001", "T001W", "ADRC",              # Company, plants, addresses
    "MARA", "MAKT", "MARC", "MARD", "MARM", "MVKE", "MBEW",  # Material master
    "MAST", "STKO", "STPO", "PLKO", "PLPO", "PLAF",           # BOMs & routings
    "EINA", "EINE", "EKKO", "EKPO", "EORD",                    # Procurement
    "VBAK", "VBAP", "VBRK", "VBRP", "LIKP", "LIPS",            # Sales
    "AFKO", "AFPO", "RESB",                                     # Manufacturing
    "KNA1", "LFA1",                                             # Partners
    "QALS", "QMEL",                                             # Quality
    "CRHD",                                                     # Work centers
    "T006", "T006A", "JEST", "TJ02T",                           # Reference / status
]


def read_csvs(csv_dir: Path) -> Dict[str, pd.DataFrame]:
    """Read every SAP CSV into a DataFrame. Returns dict keyed by table name."""
    data: Dict[str, pd.DataFrame] = {}
    for tbl in SAP_TABLES:
        path = csv_dir / f"{tbl}.csv"
        if not path.exists():
            logger.warning("CSV not found: %s — skipping", path.name)
            continue
        try:
            df = pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)
            data[tbl] = df
            logger.info("  Loaded %-8s %6d rows × %2d cols", tbl, len(df), len(df.columns))
        except Exception as e:
            logger.error("Failed to read %s: %s", path.name, e)
    return data


def compute_scope(data: Dict[str, pd.DataFrame]) -> Set[str]:
    """Compute the 'supply chain items' scope based on transactional evidence.

    Rationale: a material is only a planning item if it has OBSERVED activity.
    MARC.DISMM=PD and MARD stocking locations are not discriminating in the
    FAA — every configurable sub-assembly inherits them by default even when
    it has no real history. That causes "ghost materials" with zero demand
    and zero reorder point, which crash training_corpus.

    Scope = union of:
      1. VBAP (sales orders) — external demand observed
      2. EKPO (purchase orders) — external procurement observed
      3. RESB (reservations) — dependent demand observed
      4. AFPO (production orders) — manufacturing observed
      5. Salable MTART {FERT, HAWA, ERSA} — externally-sellable (excludes KMAT
         templates, which only become real via their variant materials)
      6. BOM seeds (MAST STLAN∈{3,5}) ∩ (has any of 1..4) — sales BOMs whose
         header has actual transactional activity. Excludes sales BOMs defined
         on configurable templates with no real sales.
      7. KMAT configurables ∩ (has any of 1..4) — only KMATs with transactions

    BOM structure (STKO/STPO) is preserved for MRP explosion, but deep
    components without transactional evidence are NOT independent products.
    """
    scope: Set[str] = set()
    mara = data.get("MARA", pd.DataFrame())
    mast = data.get("MAST", pd.DataFrame())
    vbap = data.get("VBAP", pd.DataFrame())
    ekpo = data.get("EKPO", pd.DataFrame())
    resb = data.get("RESB", pd.DataFrame())
    afpo = data.get("AFPO", pd.DataFrame())

    def _matnrs(df: pd.DataFrame, col: str = "MATNR") -> Set[str]:
        if df.empty or col not in df.columns:
            return set()
        s = set(df[col].astype(str).str.strip().unique())
        s.discard("")
        s.discard("nan")
        return s

    # Activity sets (observed transactional evidence)
    sc_sales = _matnrs(vbap)
    sc_po = _matnrs(ekpo)
    sc_resb = _matnrs(resb)
    sc_afpo = _matnrs(afpo)
    activity = sc_sales | sc_po | sc_resb | sc_afpo

    logger.info("[1] VBAP (sales demand):          %d", len(sc_sales))
    logger.info("[2] EKPO (external procurement):  %d", len(sc_po))
    logger.info("[3] RESB (dependent demand):      %d", len(sc_resb))
    logger.info("[4] AFPO (production activity):   %d", len(sc_afpo))
    logger.info("    Union (any transactional activity): %d", len(activity))

    scope |= activity

    # 5. Salable MTART (FERT/HAWA/ERSA) — exclude KMAT from blanket salable rule
    sc_salable = set()
    if not mara.empty and "MTART" in mara.columns and "MATNR" in mara.columns:
        mara_salable = mara[mara["MTART"].astype(str).str.strip().isin({"FERT", "HAWA", "ERSA"})]
        sc_salable = _matnrs(mara_salable)
        logger.info("[5] Salable MTART {FERT,HAWA,ERSA}: %d", len(sc_salable))
        scope |= sc_salable

    # 6. BOM seeds ∩ activity: sales BOMs that actually see transactions
    sc_bom_active = set()
    if not mast.empty and "STLAN" in mast.columns and "MATNR" in mast.columns:
        bom_seeds = _matnrs(
            mast[mast["STLAN"].astype(str).isin(["3", "5"])]
        )
        sc_bom_active = bom_seeds & activity
        logger.info(
            "[6] BOM seeds (STLAN∈{3,5}) with activity: %d of %d total seeds",
            len(sc_bom_active), len(bom_seeds),
        )
        scope |= sc_bom_active

    # 7. KMAT configurables with transactional activity
    sc_kmat_active = set()
    if not mara.empty and "MTART" in mara.columns and "MATNR" in mara.columns:
        kmat_mats = _matnrs(mara[mara["MTART"].astype(str).str.strip() == "KMAT"])
        sc_kmat_active = kmat_mats & activity
        logger.info(
            "[7] KMAT configurables with activity: %d of %d total KMAT",
            len(sc_kmat_active), len(kmat_mats),
        )
        scope |= sc_kmat_active

    scope.discard("")
    scope.discard("nan")
    logger.info("")
    logger.info("FINAL SCOPE (supply chain items with evidence): %d materials", len(scope))

    if not scope:
        raise ValueError("Empty scope — check data and filter criteria")

    # Breakdown by MTART for visibility
    if not mara.empty and "MTART" in mara.columns:
        mara_in_scope = mara[mara["MATNR"].astype(str).str.strip().isin(scope)]
        logger.info("Scope breakdown by MTART:")
        for mt, n in mara_in_scope["MTART"].astype(str).str.strip().value_counts().items():
            logger.info("  %-6s %d", mt, n)

    return scope


def filter_data(data: Dict[str, pd.DataFrame], scope: Set[str]) -> Dict[str, pd.DataFrame]:
    """Filter each DataFrame to only rows that reference in-scope materials.

    Key rule: BOM structure is preserved for planning items in scope. Deep
    components that are NOT in scope remain as BOM component references in
    STPO (so MRP can still explode dependent demand), but no product row is
    created for them.

    Tables keyed on MATNR are filtered to scope.
    MAST is filtered to rows whose MATNR (parent) is in scope.
    STKO/STPO are filtered to BOMs whose parent is in scope — but components
      inside those BOMs are kept even if the component material is out of scope.
    Config/topology tables are passed through.
    """
    filtered: Dict[str, pd.DataFrame] = {}

    # Identify BOM ids that are in scope (MAST parent MATNR is in scope)
    mast = data.get("MAST", pd.DataFrame())
    scoped_stlnrs: Set[str] = set()
    if not mast.empty and "MATNR" in mast.columns and "STLNR" in mast.columns:
        scoped_mast = mast[mast["MATNR"].astype(str).str.strip().isin(scope)]
        scoped_stlnrs = set(scoped_mast["STLNR"].astype(str).str.strip().dropna().tolist())
        logger.info("Scoped BOM ids (STLNR, where parent in scope): %d", len(scoped_stlnrs))

    # Also include BOMs referenced as sub-assembly inside a scoped BOM
    # (multi-level parent-child: if scoped MAST has a BOM whose components
    # are themselves BOM headers, those sub-BOMs must be kept for proper
    # explosion during MRP — but their materials stay out of product scope).
    stpo = data.get("STPO", pd.DataFrame())
    if not stpo.empty and "STLNR" in stpo.columns and "IDNRK" in stpo.columns:
        # Expand stlnrs via reachable components that are themselves MAST parents
        reachable = set(scoped_stlnrs)
        for _ in range(10):
            comps_in_reachable = stpo[stpo["STLNR"].astype(str).str.strip().isin(reachable)]
            comp_mats = set(comps_in_reachable["IDNRK"].astype(str).str.strip().dropna().tolist())
            # Find MAST entries for these components (sub-assembly BOMs)
            sub_mast = mast[mast["MATNR"].astype(str).str.strip().isin(comp_mats)] if not mast.empty else pd.DataFrame()
            if sub_mast.empty:
                break
            new_stlnrs = set(sub_mast["STLNR"].astype(str).str.strip().dropna().tolist()) - reachable
            if not new_stlnrs:
                break
            reachable |= new_stlnrs
        logger.info("BOM ids after sub-assembly expansion:           %d", len(reachable))
        scoped_stlnrs = reachable

    # Tables to filter by MATNR
    # NOTE: MAST removed — handled separately (keeps BOM-related rows even
    # when component MATNR is out of scope, to preserve BOM structure)
    matnr_filtered = {
        "MARA", "MAKT", "MARC", "MARD", "MARM", "MVKE", "MBEW",
        "PLAF", "EINA", "EKPO", "EORD",
        "VBAP", "LIPS", "VBRP", "AFPO", "RESB",
    }
    # Tables to filter by STLNR
    stlnr_filtered = {"STKO", "STPO", "PLKO", "PLPO"}

    # Tables to keep unfiltered (topology / reference / status / partners / work centers)
    passthrough = {
        "T001", "T001W", "ADRC", "T006", "T006A", "JEST", "TJ02T",
        "CRHD", "KNA1", "LFA1", "EINE", "EKKO",
        "VBAK", "VBRK", "LIKP", "AFKO",
        "QALS", "QMEL",
    }

    for name, df in data.items():
        if df.empty:
            filtered[name] = df
            continue

        # MAST: keep rows where the STLNR is in the reachable BOM set
        # (this includes parent BOMs and sub-assembly BOMs, regardless of
        # whether the MATNR of the row is in the product scope)
        if name == "MAST" and "STLNR" in df.columns:
            before = len(df)
            f = df[df["STLNR"].astype(str).str.strip().isin(scoped_stlnrs)]
            filtered[name] = f
            logger.info("  %-8s filter STLNR: %6d → %6d", name, before, len(f))
        elif name in matnr_filtered and "MATNR" in df.columns:
            before = len(df)
            f = df[df["MATNR"].astype(str).str.strip().isin(scope)]
            filtered[name] = f
            logger.info("  %-8s filter MATNR: %6d → %6d", name, before, len(f))
        elif name in stlnr_filtered and "STLNR" in df.columns:
            before = len(df)
            f = df[df["STLNR"].astype(str).str.strip().isin(scoped_stlnrs)]
            filtered[name] = f
            logger.info("  %-8s filter STLNR: %6d → %6d", name, before, len(f))
        elif name in passthrough:
            filtered[name] = df
            logger.info("  %-8s passthrough:  %6d rows", name, len(df))
        else:
            filtered[name] = df
            logger.info("  %-8s unhandled (kept as-is): %6d rows", name, len(df))

    # Secondary filter: header-level tables that reference in-scope items
    # EKKO (PO headers) — keep only orders that have at least one in-scope EKPO line
    if "EKPO" in filtered and "EKKO" in filtered and not filtered["EKPO"].empty:
        if "EBELN" in filtered["EKPO"].columns and "EBELN" in filtered["EKKO"].columns:
            in_scope_ebeln = set(filtered["EKPO"]["EBELN"].astype(str).str.strip().tolist())
            before = len(filtered["EKKO"])
            filtered["EKKO"] = filtered["EKKO"][
                filtered["EKKO"]["EBELN"].astype(str).str.strip().isin(in_scope_ebeln)
            ]
            logger.info("  EKKO    filter by EBELN: %6d → %6d", before, len(filtered["EKKO"]))

    # VBAK (SO headers) — keep only orders with in-scope VBAP items
    if "VBAP" in filtered and "VBAK" in filtered and not filtered["VBAP"].empty:
        if "VBELN" in filtered["VBAP"].columns and "VBELN" in filtered["VBAK"].columns:
            in_scope_vbeln = set(filtered["VBAP"]["VBELN"].astype(str).str.strip().tolist())
            before = len(filtered["VBAK"])
            filtered["VBAK"] = filtered["VBAK"][
                filtered["VBAK"]["VBELN"].astype(str).str.strip().isin(in_scope_vbeln)
            ]
            logger.info("  VBAK    filter by VBELN: %6d → %6d", before, len(filtered["VBAK"]))

    # LIKP (delivery headers) via LIPS
    if "LIPS" in filtered and "LIKP" in filtered and not filtered["LIPS"].empty:
        if "VBELN" in filtered["LIPS"].columns and "VBELN" in filtered["LIKP"].columns:
            in_scope_vbeln = set(filtered["LIPS"]["VBELN"].astype(str).str.strip().tolist())
            before = len(filtered["LIKP"])
            filtered["LIKP"] = filtered["LIKP"][
                filtered["LIKP"]["VBELN"].astype(str).str.strip().isin(in_scope_vbeln)
            ]
            logger.info("  LIKP    filter by VBELN: %6d → %6d", before, len(filtered["LIKP"]))

    # VBRK (billing headers) via VBRP
    if "VBRP" in filtered and "VBRK" in filtered and not filtered["VBRP"].empty:
        if "VBELN" in filtered["VBRP"].columns and "VBELN" in filtered["VBRK"].columns:
            in_scope_vbeln = set(filtered["VBRP"]["VBELN"].astype(str).str.strip().tolist())
            before = len(filtered["VBRK"])
            filtered["VBRK"] = filtered["VBRK"][
                filtered["VBRK"]["VBELN"].astype(str).str.strip().isin(in_scope_vbeln)
            ]
            logger.info("  VBRK    filter by VBELN: %6d → %6d", before, len(filtered["VBRK"]))

    # AFKO (production order headers) via AFPO
    if "AFPO" in filtered and "AFKO" in filtered and not filtered["AFPO"].empty:
        if "AUFNR" in filtered["AFPO"].columns and "AUFNR" in filtered["AFKO"].columns:
            in_scope_aufnr = set(filtered["AFPO"]["AUFNR"].astype(str).str.strip().tolist())
            before = len(filtered["AFKO"])
            filtered["AFKO"] = filtered["AFKO"][
                filtered["AFKO"]["AUFNR"].astype(str).str.strip().isin(in_scope_aufnr)
            ]
            logger.info("  AFKO    filter by AUFNR: %6d → %6d", before, len(filtered["AFKO"]))

    return filtered


async def main():
    parser = argparse.ArgumentParser(description="Build scoped SAP Demo config from CSVs")
    parser.add_argument("--csv-dir", default="imports/SAP_Demo",
                        help="Directory containing SAP CSV files (read-only)")
    parser.add_argument("--tenant-id", type=int, default=20,
                        help="Tenant id (20 = Autonomy SAP Demo)")
    parser.add_argument("--config-name", default=None,
                        help="Config name (auto-derived from T001 if omitted)")
    parser.add_argument("--delete-old", action="store_true",
                        help="Delete all existing configs for the tenant before building")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute scope and preview counts, don't write to DB")
    args = parser.parse_args()

    csv_dir = Path(args.csv_dir)
    if not csv_dir.is_absolute():
        csv_dir = Path("/app") / csv_dir
    if not csv_dir.exists():
        raise ValueError(f"CSV directory not found: {csv_dir}")

    logger.info("=" * 72)
    logger.info("SAP Demo scoped build")
    logger.info("  CSV dir:    %s", csv_dir)
    logger.info("  Tenant:     %d", args.tenant_id)
    logger.info("  Dry run:    %s", args.dry_run)
    logger.info("=" * 72)

    # 1. Load CSVs (read-only)
    logger.info("\n[1] Loading CSV files...")
    data = read_csvs(csv_dir)
    logger.info("    Loaded %d tables", len(data))

    # 2. Compute scope
    logger.info("\n[2] Computing expanded scope...")
    scope = compute_scope(data)

    # 3. Filter
    logger.info("\n[3] Filtering DataFrames to scope...")
    filtered = filter_data(data, scope)

    if args.dry_run:
        logger.info("\n[DRY RUN] Scope summary:")
        logger.info("  Materials:           %d", len(scope))
        for name in ["MARA", "MAST", "STKO", "STPO", "MARC", "MARD", "VBAP", "VBAK", "EKPO", "EKKO", "AFPO"]:
            if name in filtered:
                logger.info("  %-6s  %6d rows", name, len(filtered[name]))
        return

    # 4. Delete old configs
    from app.db.session import async_session_factory, sync_session_factory
    from sqlalchemy import text

    if args.delete_old:
        logger.info("\n[4] Deleting existing configs for tenant %d...", args.tenant_id)
        # Use the cascade delete helper from main.py (handles FK chain dynamically)
        from main import _cascade_delete_config
        sdb = sync_session_factory()
        try:
            configs = sdb.execute(
                text("SELECT id, name FROM supply_chain_configs WHERE tenant_id = :t"),
                {"t": args.tenant_id},
            ).fetchall()
            logger.info("    Found %d existing configs", len(configs))
            for cfg_id, cfg_name in configs:
                logger.info("    Cascade-deleting config %d: %s", cfg_id, cfg_name)
                try:
                    _cascade_delete_config(sdb, cfg_id)
                    sdb.commit()
                except Exception as e:
                    sdb.rollback()
                    logger.error("    Failed to delete config %d: %s", cfg_id, e)
                    raise
            logger.info("    Deleted %d configs", len(configs))
        finally:
            sdb.close()

    # 5. Build
    from app.services.sap_config_builder import SAPConfigBuilder

    config_name = args.config_name or "SAP S/4HANA 2025 (BOM-scoped)"

    logger.info("\n[5] Running SAPConfigBuilder...")
    async with async_session_factory() as db:
        builder = SAPConfigBuilder(db, tenant_id=args.tenant_id)

        async def progress(step, total, desc):
            logger.info("  [%d/%d] %s", step, total, desc)

        result = await builder.build(
            sap_data=filtered,
            config_name=config_name,
            progress_callback=progress,
        )

    logger.info("\n=== Build complete ===")
    logger.info("Result: %s", result)


if __name__ == "__main__":
    asyncio.run(main())
