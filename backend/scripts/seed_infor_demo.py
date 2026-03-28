"""
Seed Infor M3 Demo Tenant

Creates two tenants (Production + Learning) for Infor M3, loads synthetic
Midwest Industrial Supply data via InforConfigBuilder, and creates demo users
with topology-aware decision levels.

Tenant pair:
  - Autonomy Infor Demo       (PRODUCTION, admin@infor-demo.com)
  - Autonomy Infor Demo (Learning) (LEARNING, admin-learn@infor-demo.com)

Demo company: Midwest Industrial Supply
  - 6 warehouses (2 plants, 2 DCs, RM store, spare parts)
  - 57 products (21 FG, 33 RM, 3 labor)
  - 9 BOMs (pumps, valves, actuators, control panels)
  - Full transactional history (~2,040 records)

Usage:
    # From backend container:
    python scripts/seed_infor_demo.py

    # Or via Make:
    make seed-infor-demo
"""

import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Optional, Tuple

# Ensure backend is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("PYTHONPATH", str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import get_password_hash
from app.db.session import sync_engine
from app.models.tenant import Tenant, TenantMode, TenantIndustry
from app.models.user import User, UserTypeEnum, DecisionLevelEnum

DEFAULT_PASSWORD = os.getenv("AUTONOMY_DEFAULT_PASSWORD", "Autonomy@2026")

# ---------------------------------------------------------------------------
# Demo Tenant Configuration
# ---------------------------------------------------------------------------

INFOR_PROD_TENANT = {
    "name": "Autonomy Infor Demo",
    "slug": "infor-demo",
    "subdomain": "infor-demo",
    "description": "Infor M3 demo — Midwest Industrial Supply (pumps, valves, actuators)",
    "mode": TenantMode.PRODUCTION,
    "industry": TenantIndustry.INDUSTRIAL_EQUIPMENT,
    "is_demo": True,
    "admin_email": "admin@infor-demo.com",
    "admin_username": "infor_tenant_admin",
    "admin_full_name": "Infor Demo Admin",
    "config_name": "Infor M3 Midwest Industrial",
}

INFOR_LEARN_TENANT = {
    "name": "Autonomy Infor Demo (Learning)",
    "slug": "infor-learn",
    "subdomain": "infor-learn",
    "description": "Infor M3 demo — Midwest Industrial Supply (learning mode)",
    "mode": TenantMode.LEARNING,
    "industry": TenantIndustry.INDUSTRIAL_EQUIPMENT,
    "is_demo": True,
    "admin_email": "admin-learn@infor-demo.com",
    "admin_username": "infor_tenant_admin_learn",
    "admin_full_name": "Infor Demo Admin (Learning)",
    "config_name": "Infor M3 Learning Config",
}

# Demo users for the production tenant
DEMO_USERS = [
    {
        "username": "infor_exec",
        "email": "exec@infor-demo.com",
        "full_name": "Robert Hartley (CEO)",
        "decision_level": DecisionLevelEnum.EXECUTIVE,
        "user_type": UserTypeEnum.USER,
    },
    {
        "username": "infor_scvp",
        "email": "scvp@infor-demo.com",
        "full_name": "Karen Schmidt (VP Supply Chain)",
        "decision_level": DecisionLevelEnum.SC_VP,
        "user_type": UserTypeEnum.USER,
    },
    {
        "username": "infor_sopdir",
        "email": "sopdir@infor-demo.com",
        "full_name": "James Nakamura (S&OP Director)",
        "decision_level": DecisionLevelEnum.SOP_DIRECTOR,
        "user_type": UserTypeEnum.USER,
    },
    {
        "username": "infor_mps",
        "email": "mps@infor-demo.com",
        "full_name": "Lisa Fernandez (MPS Manager)",
        "decision_level": DecisionLevelEnum.MPS_MANAGER,
        "user_type": UserTypeEnum.USER,
    },
    {
        "username": "infor_atp",
        "email": "atp@infor-demo.com",
        "full_name": "David Chen (ATP Analyst)",
        "decision_level": DecisionLevelEnum.ATP_ANALYST,
        "user_type": UserTypeEnum.USER,
    },
    {
        "username": "infor_rebal",
        "email": "rebalancing@infor-demo.com",
        "full_name": "Maria Santos (Rebalancing Analyst)",
        "decision_level": DecisionLevelEnum.REBALANCING_ANALYST,
        "user_type": UserTypeEnum.USER,
    },
    {
        "username": "infor_po",
        "email": "po@infor-demo.com",
        "full_name": "Thomas Wilson (PO Analyst)",
        "decision_level": DecisionLevelEnum.PO_ANALYST,
        "user_type": UserTypeEnum.USER,
    },
    {
        "username": "infor_ot",
        "email": "ordertracking@infor-demo.com",
        "full_name": "Jennifer Park (Order Tracking)",
        "decision_level": DecisionLevelEnum.ORDER_TRACKING_ANALYST,
        "user_type": UserTypeEnum.USER,
    },
]


def _slugify(value: str) -> str:
    """Convert string to URL-safe slug."""
    slug = re.sub(r"[^0-9a-zA-Z]+", "-", value.strip().lower()).strip("-")
    return slug or "config"


# ---------------------------------------------------------------------------
# Tenant + User Creation
# ---------------------------------------------------------------------------

def create_or_get_user(
    db: Session,
    username: str,
    email: str,
    full_name: str,
    user_type: UserTypeEnum,
    tenant_id: Optional[int] = None,
    decision_level: Optional[DecisionLevelEnum] = None,
) -> User:
    """Create a user or update existing one with correct attributes."""
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        updated = False
        if existing.user_type != user_type:
            existing.user_type = user_type
            updated = True
        if existing.decision_level != decision_level:
            existing.decision_level = decision_level
            updated = True
        if existing.is_superuser:
            existing.is_superuser = False
            updated = True
        if tenant_id and existing.tenant_id != tenant_id:
            existing.tenant_id = tenant_id
            updated = True
        if existing.full_name != full_name:
            existing.full_name = full_name
            updated = True
        if updated:
            db.flush()
        return existing

    user = User(
        username=username,
        email=email,
        full_name=full_name,
        hashed_password=get_password_hash(DEFAULT_PASSWORD),
        user_type=user_type,
        tenant_id=tenant_id,
        decision_level=decision_level,
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    db.flush()
    return user


def create_or_get_tenant(
    db: Session,
    spec: dict,
    admin_user: User,
) -> Tenant:
    """Create or update a tenant from spec dict."""
    existing = db.query(Tenant).filter(Tenant.name == spec["name"]).first()
    if existing:
        # Update fields
        if existing.admin_id != admin_user.id:
            existing.admin_id = admin_user.id
        existing.industry = spec.get("industry")
        existing.is_demo = spec.get("is_demo", True)
        existing.mode = spec["mode"]
        db.flush()
        print(f"  Tenant '{existing.name}' already exists (id={existing.id})")
        return existing

    tenant = Tenant(
        name=spec["name"],
        slug=spec["slug"],
        subdomain=spec["subdomain"],
        description=spec["description"],
        admin_id=admin_user.id,
        mode=spec["mode"],
        industry=spec.get("industry"),
        is_demo=spec.get("is_demo", True),
    )
    # Apply industry-specific simulation defaults
    if tenant.industry:
        tenant.apply_industry_sim_defaults()

    db.add(tenant)
    db.flush()
    print(f"  Created tenant '{tenant.name}' (id={tenant.id})")
    return tenant


def create_supply_chain_config(
    db: Session,
    tenant_id: int,
    config_name: str,
    admin_id: int,
) -> int:
    """Create a SupplyChainConfig for the tenant, return config_id."""
    from app.models.supply_chain_config import SupplyChainConfig

    existing = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.tenant_id == tenant_id,
        SupplyChainConfig.name == config_name,
    ).first()
    if existing:
        print(f"  Config '{config_name}' already exists (id={existing.id})")
        return existing.id

    config = SupplyChainConfig(
        tenant_id=tenant_id,
        name=config_name,
        description="Infor M3 supply chain configuration for Midwest Industrial Supply",
        created_by=admin_id,
        is_active=True,
    )
    db.add(config)
    db.flush()
    print(f"  Created config '{config_name}' (id={config.id})")
    return config.id


# ---------------------------------------------------------------------------
# Data Loading (async → sync bridge)
# ---------------------------------------------------------------------------

async def load_infor_data(config_id: int, tenant_id: int):
    """Generate demo data and load via InforConfigBuilder."""
    import tempfile
    from app.db.session import async_session_factory

    # Step 1: Generate demo data to temp dir
    tmpdir = tempfile.mkdtemp(prefix="infor_demo_")
    print(f"\n  Generating Infor demo data → {tmpdir}/")

    # Import and run the generator
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from generate_infor_demo_data import main as generate_main
    import generate_infor_demo_data as gen_module

    gen_module.OUTPUT_DIR = Path(tmpdir)
    generate_main()

    # Step 2: Load via InforConfigBuilder
    print(f"\n  Loading data into config {config_id}...")
    from app.integrations.infor.config_builder import InforConfigBuilder

    async with async_session_factory() as session:
        builder = InforConfigBuilder(db=session, tenant_id=tenant_id)
        result = await builder.build_from_csv(
            csv_dir=tmpdir,
            config_name="Infor M3 Midwest Industrial",
            config_id=config_id,
        )
        await session.commit()

    print(f"\n  Build result: {'OK' if result.success else 'FAILED'}")
    print(f"    Sites: {result.sites_created}")
    print(f"    Products: {result.products_created}")
    print(f"    Trading Partners: {result.trading_partners_created}")
    print(f"    Lanes: {result.lanes_created}")
    print(f"    BOMs: {result.boms_created}")
    print(f"    Inv Levels: {result.inv_levels_created}")
    print(f"    Inv Policies: {result.inv_policies_created}")
    print(f"    Purchase Orders: {result.purchase_orders_created}")
    print(f"    Outbound Orders: {result.outbound_orders_created}")
    print(f"    Production Orders: {result.production_orders_created}")
    print(f"    Shipments: {result.shipments_created}")
    print(f"    Forecasts: {result.forecasts_created}")

    if result.warnings:
        print(f"    Warnings: {len(result.warnings)}")
    if result.errors:
        print(f"    ERRORS: {result.errors}")

    # Cleanup temp dir
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    """Seed Infor M3 demo tenants with full data pipeline."""
    print("\n" + "=" * 70)
    print("  Infor M3 Demo Tenant Provisioning")
    print("  Demo Company: Midwest Industrial Supply")
    print("=" * 70)

    SyncSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=sync_engine,
    )
    db: Session = SyncSessionLocal()

    try:
        # ── Step 1: Production Tenant ────────────────────────────────────
        print("\n[1/6] Creating Production tenant admin...")
        prod_admin = create_or_get_user(
            db,
            username=INFOR_PROD_TENANT["admin_username"],
            email=INFOR_PROD_TENANT["admin_email"],
            full_name=INFOR_PROD_TENANT["admin_full_name"],
            user_type=UserTypeEnum.TENANT_ADMIN,
            decision_level=DecisionLevelEnum.DEMO_ALL,
        )
        db.commit()

        print("\n[2/6] Creating Production tenant...")
        prod_tenant = create_or_get_tenant(db, INFOR_PROD_TENANT, prod_admin)
        prod_admin.tenant_id = prod_tenant.id
        db.commit()

        # ── Step 2: Learning Tenant ──────────────────────────────────────
        print("\n[3/6] Creating Learning tenant...")
        learn_admin = create_or_get_user(
            db,
            username=INFOR_LEARN_TENANT["admin_username"],
            email=INFOR_LEARN_TENANT["admin_email"],
            full_name=INFOR_LEARN_TENANT["admin_full_name"],
            user_type=UserTypeEnum.TENANT_ADMIN,
            decision_level=DecisionLevelEnum.DEMO_ALL,
        )
        db.commit()

        learn_tenant = create_or_get_tenant(db, INFOR_LEARN_TENANT, learn_admin)
        learn_admin.tenant_id = learn_tenant.id
        db.commit()

        # ── Step 3: Supply Chain Configs ─────────────────────────────────
        print("\n[4/6] Creating Supply Chain Configs...")
        prod_config_id = create_supply_chain_config(
            db, prod_tenant.id, INFOR_PROD_TENANT["config_name"], prod_admin.id,
        )
        learn_config_id = create_supply_chain_config(
            db, learn_tenant.id, INFOR_LEARN_TENANT["config_name"], learn_admin.id,
        )

        # Set default_config_id on admin users
        prod_admin.default_config_id = prod_config_id
        learn_admin.default_config_id = learn_config_id
        db.commit()

        # ── Step 4: Demo Users (Production tenant) ───────────────────────
        print("\n[5/6] Creating demo users...")
        for user_spec in DEMO_USERS:
            user = create_or_get_user(
                db,
                username=user_spec["username"],
                email=user_spec["email"],
                full_name=user_spec["full_name"],
                user_type=user_spec["user_type"],
                tenant_id=prod_tenant.id,
                decision_level=user_spec["decision_level"],
            )
            user.default_config_id = prod_config_id
            print(f"    {user_spec['email']} ({user_spec['decision_level'].value})")

        db.commit()

        # ── Step 5: Load Demo Data ───────────────────────────────────────
        print("\n[6/6] Loading Infor M3 demo data...")

        # Load into both configs in a single event loop
        async def _load_both():
            print(f"\n  → Production config (id={prod_config_id}):")
            await load_infor_data(prod_config_id, prod_tenant.id)
            print(f"\n  → Learning config (id={learn_config_id}):")
            await load_infor_data(learn_config_id, learn_tenant.id)

        asyncio.run(_load_both())

        # ── Summary ──────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("  Infor Demo Provisioning Complete")
        print("=" * 70)
        print(f"\n  Production Tenant:")
        print(f"    Name:   {prod_tenant.name} (id={prod_tenant.id})")
        print(f"    Admin:  {INFOR_PROD_TENANT['admin_email']}")
        print(f"    Config: {INFOR_PROD_TENANT['config_name']} (id={prod_config_id})")
        print(f"    Users:  {len(DEMO_USERS) + 1} ({len(DEMO_USERS)} demo + 1 admin)")
        print(f"\n  Learning Tenant:")
        print(f"    Name:   {learn_tenant.name} (id={learn_tenant.id})")
        print(f"    Admin:  {INFOR_LEARN_TENANT['admin_email']}")
        print(f"    Config: {INFOR_LEARN_TENANT['config_name']} (id={learn_config_id})")
        print(f"\n  Login: any @infor-demo.com email / {DEFAULT_PASSWORD}")
        print(f"  URL:   http://localhost:8088")
        print()

    except Exception as e:
        print(f"\n  ERROR: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
