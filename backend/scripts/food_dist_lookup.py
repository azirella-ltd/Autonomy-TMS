"""
Dynamic Food Dist Config Lookup

Resolves config_id, tenant_id, admin_user_id, and site IDs by querying the
database instead of using hardcoded values. All Food Dist seed scripts should
import from here instead of hardcoding IDs.

Usage:
    from scripts.food_dist_lookup import resolve_food_dist_ids

    ids = resolve_food_dist_ids()
    CONFIG_ID = ids["config_id"]
    TENANT_ID = ids["tenant_id"]
    ADMIN_USER_ID = ids["admin_user_id"]
    DC_SITE_ID = ids["dc_site_id"]
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import text


def resolve_food_dist_ids(engine=None, db=None):
    """Resolve all Food Dist IDs dynamically from the database.

    Looks up the Food Dist config by tenant slug='food-dist', then resolves
    all downstream IDs (sites, users, company) from that config.

    Args:
        engine: SQLAlchemy engine (used if db not provided)
        db: SQLAlchemy session (preferred)

    Returns:
        dict with keys: config_id, tenant_id, admin_user_id, dc_site_id,
        company_id, site_ids (dict name→id), supplier_sites, customer_sites
    """
    if db is None and engine is None:
        from app.db.session import sync_session_factory
        db = sync_session_factory()
        _close_db = True
    else:
        _close_db = False

    def _exec(sql, params=None):
        if db is not None:
            return db.execute(text(sql), params or {})
        else:
            with engine.connect() as conn:
                return conn.execute(text(sql), params or {})

    # 1. Find the Food Dist config via tenant slug
    row = _exec(
        "SELECT sc.id, sc.tenant_id, t.admin_id "
        "FROM supply_chain_configs sc "
        "JOIN tenants t ON t.id = sc.tenant_id "
        "WHERE t.slug = 'food-dist' "
        "ORDER BY sc.id DESC LIMIT 1"
    ).fetchone()

    if not row:
        # Fallback: try by config name
        row = _exec(
            "SELECT sc.id, sc.tenant_id, t.admin_id "
            "FROM supply_chain_configs sc "
            "JOIN tenants t ON t.id = sc.tenant_id "
            "WHERE sc.name ILIKE '%%food%%dist%%' "
            "ORDER BY sc.id DESC LIMIT 1"
        ).fetchone()

    if not row:
        print("ERROR: Food Dist config not found. Run seed_food_dist_demo.py first.")
        sys.exit(1)

    config_id = row[0]
    tenant_id = row[1]
    admin_user_id = row[2]

    # 2. Resolve site IDs by name
    site_rows = _exec(
        "SELECT id, name, master_type FROM site WHERE config_id = :cid",
        {"cid": config_id}
    ).fetchall()

    site_ids = {r[1]: r[0] for r in site_rows}
    dc_site_id = site_ids.get("CDC_WEST")

    supplier_sites = [(r[0], r[1]) for r in site_rows if r[2] == "VENDOR"]
    customer_sites = [(r[0], r[1]) for r in site_rows if r[2] == "CUSTOMER"]

    # 3. Resolve company_id
    comp_row = _exec(
        "SELECT company_id FROM site WHERE config_id = :cid AND company_id IS NOT NULL LIMIT 1",
        {"cid": config_id}
    ).fetchone()
    company_id = comp_row[0] if comp_row else None

    if _close_db and db is not None:
        db.close()

    result = {
        "config_id": config_id,
        "tenant_id": tenant_id,
        "admin_user_id": admin_user_id,
        "dc_site_id": dc_site_id,
        "company_id": company_id,
        "site_ids": site_ids,
        "supplier_sites": supplier_sites,
        "customer_sites": customer_sites,
    }

    print(f"Food Dist resolved: config_id={config_id}, tenant_id={tenant_id}, "
          f"dc_site_id={dc_site_id}, {len(site_ids)} sites")

    return result


if __name__ == "__main__":
    ids = resolve_food_dist_ids()
    for k, v in ids.items():
        if k in ("site_ids", "supplier_sites", "customer_sites"):
            print(f"  {k}: {len(v)} entries")
        else:
            print(f"  {k}: {v}")
