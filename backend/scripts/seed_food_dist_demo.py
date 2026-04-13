#!/usr/bin/env python3
"""
Seed Food Dist Demo - Powell Framework Aligned Users

Creates a Food Dist tenant with users aligned to Powell SDAM levels:

Primary Demo User (recommended for demos):
- demo: Combined user with ALL Powell capabilities (no login/logout needed!)
        Lands on Executive Dashboard, can navigate to all Powell views

Individual Role Users (for testing specific role flows):
- sc_vp: VP of Supply Chain (Strategic/CFA level) → Executive Dashboard
- sop_director: S&OP Director (Tactical/S&OP level) → S&OP Worklist
- mps_manager: MPS/Execution Manager (Operational/TRM level) → Agent Decisions

Usage:
    # Run via docker compose
    docker compose exec backend python scripts/seed_us_foods_demo.py

    # Or directly with venv
    cd backend && python scripts/seed_us_foods_demo.py

Demo Flow:
    1. Login as demo@distdemo.com (password: Autonomy@2026)
    2. Executive Dashboard shown by default
    3. Navigate to S&OP Worklist, Decision Performance via nav menu
    4. All Powell dashboards accessible without logout
"""

import os
import sys
import asyncio
from pathlib import Path

# Ensure backend package is importable
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy.orm import Session, sessionmaker
from app.db.session import sync_engine
from app.models.user import User, UserTypeEnum, DecisionLevelEnum
from app.models.tenant import Tenant, TenantMode
from app.models.rbac import Role, Permission
from app.core.security import get_password_hash
from app.core.capabilities import (
    Capability,
    CapabilitySet,
    SC_VP_CAPABILITIES,
    SOP_DIRECTOR_CAPABILITIES,
    MPS_MANAGER_CAPABILITIES,
    ATP_ANALYST_CAPABILITIES,
    REBALANCING_ANALYST_CAPABILITIES,
    PO_ANALYST_CAPABILITIES,
    ORDER_TRACKING_ANALYST_CAPABILITIES,
    ALLOCATION_MANAGER_CAPABILITIES,
    ORDER_PROMISE_MANAGER_CAPABILITIES,
)
from app.services.rbac_service import RBACService, seed_default_permissions
from app.services.agent_human_mapping import (
    recommend_users,
    classify_site_roles,
    SiteInfo,
    LaneInfo,
    SiteRole,
    format_recommendations,
    format_site_analysis,
)


# =============================================================================
# Food Dist Demo Configuration
# =============================================================================

FOOD_DIST_CUSTOMER_NAME = "Food Dist"
FOOD_DIST_DESCRIPTION = "Food Dist - America's largest food redistributor. Powell Framework demo."
DEFAULT_PASSWORD = os.getenv("AUTONOMY_DEFAULT_PASSWORD", "Autonomy@2026")

# Persona names for auto-generated users (keyed by decision_level)
PERSONA_NAMES = {
    "SC_VP": ("sc_vp", "scvp@distdemo.com", "Sarah Chen (VP Supply Chain)"),
    "SOP_DIRECTOR": ("sop_director", "sopdir@distdemo.com", "Michael Torres (S&OP Director)"),
    "MPS_MANAGER": ("mps_manager", "mpsmanager@distdemo.com", "Jennifer Park (MPS Manager)"),
    "ATP_ANALYST": ("atp_analyst", "atp@distdemo.com", "David Kim (ATP Analyst)"),
    "REBALANCING_ANALYST": ("rebalancing_analyst", "rebalancing@distdemo.com", "Maria Santos (Rebalancing Analyst)"),
    "PO_ANALYST": ("po_analyst", "po@distdemo.com", "James Wilson (PO Analyst)"),
    "ORDER_TRACKING_ANALYST": ("order_tracking_analyst", "ordertracking@distdemo.com", "Lisa Chen (Order Tracking Analyst)"),
}

# Fixed users always seeded (admin + executive + demo-all)
FIXED_USERS = [
    # ==========================================================================
    # TENANT ADMIN: Full access within tenant + DEMO_ALL for executive landing
    # ==========================================================================
    {
        "username": "fd_tenant_admin",
        "email": "admin@distdemo.com",
        "full_name": "Food Dist Admin",
        "user_type": UserTypeEnum.TENANT_ADMIN,
        "is_tenant_admin": True,
        "decision_level": "DEMO_ALL",
        "site_scope": None,
        "product_scope": None,
    },
    # ==========================================================================
    # EXECUTIVE (CEO): Read-only strategic view
    # ==========================================================================
    {
        "username": "exec",
        "email": "exec@distdemo.com",
        "full_name": "Executive (CEO)",
        "user_type": UserTypeEnum.USER,
        "is_tenant_admin": False,
        "decision_level": "EXECUTIVE",
        "site_scope": None,
        "product_scope": None,
    },
]


def build_topology_aware_users(db: Session, tenant_id: int) -> list:
    """Build user list from actual DAG topology using agent-human mapping.

    Reads the config's sites and lanes, classifies site roles (hub/spoke/
    factory/standalone), then generates one user per decision_level with
    correct site_scope derived from the topology.

    Falls back to fixed planning-level users if no config found.
    """
    from app.models.supply_chain_config import (
        SupplyChainConfig,
        Site,
        TransportationLane,
    )

    # Find config for this tenant
    config = (
        db.query(SupplyChainConfig)
        .filter(
            SupplyChainConfig.tenant_id == tenant_id,
            SupplyChainConfig.is_active == True,
        )
        .first()
    )
    if not config:
        print("  Warning: no active config found — using planning-level users only")
        return _fallback_planning_users()

    # Load sites and lanes
    db_sites = db.query(Site).filter(Site.config_id == config.id).all()
    db_lanes = (
        db.query(TransportationLane)
        .filter(TransportationLane.config_id == config.id)
        .all()
    )

    # Convert to mapping dataclasses
    sites = []
    for s in db_sites:
        mt = (s.master_type or "inventory").lower()
        is_ext = bool(getattr(s, "is_external", False))
        tpt = getattr(s, "tpartner_type", None)
        if tpt in ("vendor", "customer"):
            is_ext = True
            mt = tpt
        site_key = f"SITE_{s.name}" if s.name else str(s.id)
        sites.append(SiteInfo(
            id=s.id, key=site_key, name=s.name or str(s.id),
            master_type=mt,
            sc_site_type=getattr(s, "type", None),
            dag_type=getattr(s, "dag_type", None),
            is_external=is_ext,
        ))

    lanes = []
    for ln in db_lanes:
        if ln.from_site_id and ln.to_site_id:
            lanes.append(LaneInfo(
                source_site_id=ln.from_site_id,
                dest_site_id=ln.to_site_id,
            ))

    # Generate recommendations from topology
    recs = recommend_users(sites, lanes)

    # Print analysis
    classify_site_roles(sites, lanes)
    print(format_site_analysis(sites))
    print(format_recommendations(recs))

    # Convert recommendations to user dicts
    users = []
    for rec in recs:
        persona = PERSONA_NAMES.get(rec.decision_level)
        if not persona:
            continue
        username, email, full_name = persona
        users.append({
            "username": username,
            "email": email,
            "full_name": full_name,
            "user_type": UserTypeEnum.USER,
            "is_tenant_admin": False,
            "decision_level": rec.decision_level,
            "site_scope": rec.site_scope if rec.site_scope else None,
            "product_scope": None,
        })

    return users


def _fallback_planning_users() -> list:
    """Minimal planning-level users when no config exists yet."""
    users = []
    for dl in ["SC_VP", "SOP_DIRECTOR", "MPS_MANAGER"]:
        persona = PERSONA_NAMES.get(dl)
        if persona:
            username, email, full_name = persona
            users.append({
                "username": username,
                "email": email,
                "full_name": full_name,
                "user_type": UserTypeEnum.USER,
                "is_tenant_admin": False,
                "decision_level": dl,
                "site_scope": None,
                "product_scope": None,
            })
    return users

# Powell role to capability set mapping
POWELL_ROLE_CAPABILITIES = {
    "SC_VP": SC_VP_CAPABILITIES,
    "SOP_DIRECTOR": SOP_DIRECTOR_CAPABILITIES,
    "MPS_MANAGER": MPS_MANAGER_CAPABILITIES,
    "ATP_ANALYST": ATP_ANALYST_CAPABILITIES,
    "REBALANCING_ANALYST": REBALANCING_ANALYST_CAPABILITIES,
    "PO_ANALYST": PO_ANALYST_CAPABILITIES,
    "ORDER_TRACKING_ANALYST": ORDER_TRACKING_ANALYST_CAPABILITIES,
    "ALLOCATION_MANAGER": ALLOCATION_MANAGER_CAPABILITIES,
    "ORDER_PROMISE_MANAGER": ORDER_PROMISE_MANAGER_CAPABILITIES,
}

# Combined capability set for demo user (union of all Powell roles including TRM specialists)
DEMO_ALL_CAPABILITIES = CapabilitySet(
    capabilities=(
        SC_VP_CAPABILITIES.capabilities |
        SOP_DIRECTOR_CAPABILITIES.capabilities |
        MPS_MANAGER_CAPABILITIES.capabilities |
        ATP_ANALYST_CAPABILITIES.capabilities |
        REBALANCING_ANALYST_CAPABILITIES.capabilities |
        PO_ANALYST_CAPABILITIES.capabilities |
        ORDER_TRACKING_ANALYST_CAPABILITIES.capabilities
    )
)
POWELL_ROLE_CAPABILITIES["DEMO_ALL"] = DEMO_ALL_CAPABILITIES


def create_or_get_user(
    db: Session,
    username: str,
    email: str,
    full_name: str,
    user_type: UserTypeEnum,
    tenant_id: int,
    decision_level: DecisionLevelEnum = None,
    site_scope: list = None,
    product_scope: list = None,
) -> User:
    """Create a user or update existing one with correct attributes.

    Args:
        decision_level: Decision level that determines landing page.
                        Separate from capabilities which can be customized.
    """
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        # Update existing user to ensure correct user_type and attributes
        updated = False
        if existing.user_type != user_type:
            print(f"  Updating user '{username}' user_type: {existing.user_type.value} -> {user_type.value}")
            existing.user_type = user_type
            updated = True
        # existing.decision_level is str (canonical column); decision_level param is DecisionLevelEnum
        if existing.decision_level != decision_level:
            old_role = existing.decision_level if existing.decision_level else None
            new_role = decision_level.value if decision_level else None
            print(f"  Updating user '{username}' decision_level: {old_role} -> {new_role}")
            existing.decision_level = decision_level
            updated = True
        if existing.site_scope != site_scope:
            existing.site_scope = site_scope
            updated = True
        if existing.product_scope != product_scope:
            existing.product_scope = product_scope
            updated = True
        # Always enforce is_superuser=False for seeded users (only SYSTEM_ADMIN should be superuser)
        if existing.is_superuser:
            print(f"  Fixing user '{username}' is_superuser: True -> False")
            existing.is_superuser = False
            updated = True
        if tenant_id and existing.tenant_id != tenant_id:
            existing.tenant_id = tenant_id
            updated = True
        if updated:
            db.flush()
            print(f"  User '{username}' updated (id={existing.id})")
        else:
            print(f"  User '{username}' already exists (id={existing.id})")
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
        site_scope=site_scope,
        product_scope=product_scope,
    )
    db.add(user)
    db.flush()
    dl_str = decision_level.value if decision_level else "None"
    print(f"  Created user '{username}' (id={user.id}, type={user_type.value}, decision_level={dl_str})")
    return user


def create_or_get_tenant(db: Session, admin_user: User) -> Tenant:
    """Create Food Dist tenant or return existing one.

    Looks for tenant by exact name first, then by partial match
    (handles 'Food Dist' vs 'Food Distributor' mismatch).
    """
    from sqlalchemy import or_
    existing = db.query(Tenant).filter(
        or_(
            Tenant.name == FOOD_DIST_CUSTOMER_NAME,
            Tenant.name.ilike("Food Dist%"),
            Tenant.name.ilike("%Food%Dist%"),
            Tenant.slug == "food-dist",
        )
    ).first()
    if existing:
        print(f"Tenant '{existing.name}' already exists (id={existing.id})")
        # Ensure admin_id is set
        if existing.admin_id != admin_user.id:
            existing.admin_id = admin_user.id
            db.flush()
            print(f"  Updated admin_id to {admin_user.id}")
        return existing

    tenant = Tenant(
        name=FOOD_DIST_CUSTOMER_NAME,
        description=FOOD_DIST_DESCRIPTION,
        admin_id=admin_user.id,
        mode=TenantMode.PRODUCTION,  # Operational tenant
    )
    db.add(tenant)
    db.flush()
    print(f"Created tenant '{FOOD_DIST_CUSTOMER_NAME}' (id={tenant.id})")
    return tenant


def create_decision_level_role(
    db: Session,
    rbac_service: RBACService,
    role_name: str,
    customer_id: int = None,
) -> Role:
    """Create a Powell-aligned role with appropriate capabilities.

    Uses tenant_id=None to create global roles that work across all tenants.
    The customer_id is used for naming/description purposes only.
    """
    slug = role_name.lower().replace(" ", "-")

    # Check if role already exists (global role with tenant_id=None)
    existing = rbac_service.get_role_by_slug(slug, tenant_id=None)
    if existing:
        # Update permissions on existing role to pick up new capabilities
        capability_set_update = POWELL_ROLE_CAPABILITIES.get(role_name)
        if capability_set_update:
            permission_names_update = [cap.value for cap in capability_set_update.capabilities]
            existing.permissions.clear()
            for perm_name in permission_names_update:
                permission = rbac_service.get_permission_by_name(perm_name)
                if permission:
                    existing.permissions.append(permission)
            db.commit()
            db.refresh(existing)
            print(f"  Updated role '{role_name}' (id={existing.id}, permissions={len(existing.permissions)})")
        else:
            print(f"  Role '{role_name}' already exists (id={existing.id})")
        return existing

    # Get capability set for this role
    capability_set = POWELL_ROLE_CAPABILITIES.get(role_name)
    if not capability_set:
        raise ValueError(f"Unknown Powell role: {role_name}")

    # Convert capabilities to permission names
    permission_names = [cap.value for cap in capability_set.capabilities]

    # Create role with permissions (tenant_id=None for global role)
    role = rbac_service.create_role(
        name=f"Powell {role_name.replace('_', ' ').title()}",
        slug=slug,
        description=f"Powell Framework {role_name} role - Strategic/Tactical/Operational",
        tenant_id=None,  # Global role (not tenant-scoped)
        permission_names=permission_names,
        is_system=True,  # System role so it's protected
    )
    print(f"  Created role '{role.name}' (id={role.id}, permissions={len(role.permissions)})")
    return role


def _generate_sc_config_for_group(tenant_id: int):
    """Generate Food Dist SC config for an existing tenant using async generator."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker as async_sessionmaker
    from app.core.db_urls import resolve_async_database_url
    from app.services.food_dist_config_generator import generate_food_dist_config

    async def _run():
        async_db_url = resolve_async_database_url()
        engine = create_async_engine(async_db_url)
        AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with AsyncSessionLocal() as session:
            try:
                result = await generate_food_dist_config(
                    db=session,
                    existing_tenant_id=tenant_id,
                )
                config_id = result.get("config_id")
                status = result.get("summary", {}).get("status")
                if status == "already_exists":
                    print(f"  SC config already exists for tenant {tenant_id} (config_id={config_id})")
                else:
                    print(f"  Created SC config (id={config_id}) with:")
                    print(f"    Suppliers: {result.get('suppliers_created', 0)}")
                    print(f"    Customers: {result.get('customers_created', 0)}")
                    print(f"    Products: {result.get('products_created', 0)}")
                    print(f"    Lanes: {result.get('lanes_created', 0)}")
            except Exception as e:
                print(f"  Warning: SC config generation failed: {e}")
                await session.rollback()
        await engine.dispose()

    asyncio.run(_run())


def main():
    """Seed Food Dist demo setup."""
    print("=" * 70)
    print("Seeding Food Dist Demo - Powell Framework Aligned Users")
    print("=" * 70)

    # Create database session
    SyncSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=sync_engine
    )
    db: Session = SyncSessionLocal()

    try:
        # Step 1: Ensure permissions are seeded
        print("\n1. Ensuring permissions are seeded...")
        seed_default_permissions(db)

        # Step 2: Create tenant admin user first (needed for tenant creation)
        print("\n2. Creating tenant admin user...")
        admin_config = next(u for u in FIXED_USERS if u["is_tenant_admin"])
        admin_user = create_or_get_user(
            db=db,
            username=admin_config["username"],
            email=admin_config["email"],
            full_name=admin_config["full_name"],
            user_type=admin_config["user_type"],
            tenant_id=None,  # Will be updated after tenant creation
        )
        db.commit()

        # Step 3: Create Food Dist tenant
        print("\n3. Creating Food Dist tenant...")
        tenant = create_or_get_tenant(db, admin_user)

        # Update admin user's tenant_id
        admin_user.tenant_id = tenant.id
        db.commit()

        # Step 4: Create RBAC service and Powell roles
        print("\n4. Creating Powell-aligned RBAC roles...")
        rbac_service = RBACService(db)

        level_roles = {}
        for role_name in POWELL_ROLE_CAPABILITIES.keys():
            role = create_decision_level_role(db, rbac_service, role_name, customer_id=tenant.id)
            level_roles[role_name] = role

        db.commit()

        # Step 5: Build topology-aware user list from DAG analysis
        print("\n5. Analyzing DAG topology for agent-human mapping...")
        topology_users = build_topology_aware_users(db, tenant.id)
        DEMO_USERS = FIXED_USERS + topology_users

        # Step 6: Create users and assign roles
        print("\n6. Creating Powell-aligned users...")
        for user_config in DEMO_USERS:
            if user_config.get("is_tenant_admin"):
                continue  # Already created

            # Convert decision_level string to enum (if specified)
            dl_str = user_config.get("decision_level")
            dl_enum = None
            if dl_str:
                try:
                    dl_enum = DecisionLevelEnum(dl_str)
                except ValueError:
                    print(f"  Warning: Unknown decision_level '{dl_str}', skipping")

            user = create_or_get_user(
                db=db,
                username=user_config["username"],
                email=user_config["email"],
                full_name=user_config["full_name"],
                user_type=user_config["user_type"],
                tenant_id=tenant.id,
                decision_level=dl_enum,  # Store on user for landing page routing
                site_scope=user_config.get("site_scope"),
                product_scope=user_config.get("product_scope"),
            )

            # Assign RBAC role for capabilities (can be customized by tenant admin)
            if dl_str:
                role = level_roles.get(dl_str)
                if role and role not in user.roles:
                    user.roles.append(role)
                    print(f"    Assigned RBAC role '{role.name}' to '{user.username}'")

        db.commit()

        # Step 7: Generate Food Dist SC config for this tenant (async)
        print("\n7. Generating Food Dist supply chain config for tenant...")
        _generate_sc_config_for_group(tenant.id)

        # Step 8: Print summary
        print("\n" + "=" * 70)
        print("Food Dist Demo Setup Complete!")
        print("=" * 70)
        print(f"\nTenant: {FOOD_DIST_CUSTOMER_NAME} (ID: {tenant.id})")
        print(f"Mode: {tenant.mode.value}")
        print(f"\nUsers created (password: {DEFAULT_PASSWORD}):")
        print("-" * 50)

        for user_config in DEMO_USERS:
            dl = user_config.get("decision_level", "TENANT_ADMIN")
            level = {
                "SC_VP": "Strategic/CFA",
                "SOP_DIRECTOR": "Tactical/S&OP",
                "MPS_MANAGER": "Operational/TRM",
                "ATP_ANALYST": "Execution/ATP TRM",
                "REBALANCING_ANALYST": "Execution/Rebalancing TRM",
                "PO_ANALYST": "Execution/PO Creation TRM",
                "ORDER_TRACKING_ANALYST": "Execution/Order Tracking TRM",
                "DEMO_ALL": "ALL LEVELS (Demo)",
                None: "Admin",
            }.get(dl, "Unknown")

            print(f"  {user_config['username']:<20} | {user_config['email']:<30}")
            print(f"    Powell Level: {level}")
            if user_config.get("site_scope"):
                print(f"    Site Scope: {user_config['site_scope']}")
            if user_config.get("product_scope"):
                print(f"    Product Scope: {user_config['product_scope']}")
            print()

        print("\nPowell Framework Role Mapping:")
        print("-" * 70)
        print("  demo                 -> ALL LEVELS: Full access for demos (no login/logout)")
        print("  sc_vp                -> Strategic: Policy θ, approvals, S&OP Policy (L1)")
        print("  sop_director         -> Tactical: MPS candidates (L2), Supply/Allocation (L3-L4)")
        print("  mps_manager          -> Operational: Supply/Allocation (L3-L4), Execution (L5)")
        print("  atp_analyst          -> Execution: ATP fulfillment decisions (accept/override)")
        print("  rebalancing_analyst  -> Execution: Inventory transfer decisions (accept/override)")
        print("  po_analyst           -> Execution: Purchase order decisions (accept/override)")
        print("  order_tracking_analyst -> Execution: Exception handling (accept/override)")
        print()
        print("\nPlanning Cascade Layer Access (Nav: Planning Cascade):")
        print("-" * 70)
        print("  Page                  | sc_vp  | sop_dir | mps_mgr | trm_specialist")
        print("  Cascade Dashboard     | view   | view    | view    | view")
        print("  S&OP Policy (L1)      | manage | view    | view    | -")
        print("  Supply Baseline (L2)  | view   | manage  | view    | -")
        print("  Supply Worklist (L3)  | view   | manage  | manage  | -")
        print("  Allocation Wkl. (L4)  | view   | manage  | manage  | -")
        print("  Execution (L5)        | view   | view    | manage  | view")
        print("  ATP Worklist          | -      | -       | manage  | manage (ATP only)")
        print("  Rebalancing Worklist  | -      | -       | manage  | manage (Reb. only)")
        print("  PO Worklist           | -      | -       | manage  | manage (PO only)")
        print("  Order Tracking Wkl.   | -      | -       | manage  | manage (OT only)")
        print()
        print("\nTRM Override → RL Training Feedback Loop:")
        print("-" * 70)
        print("  1. TRM agent proposes decision (PROPOSED status)")
        print("  2. Specialist reviews in worklist (confidence, context, reasoning)")
        print("  3. Accept/Override/Reject with reason code + free text")
        print("  4. Override values written to trm_replay_buffer (is_expert=True)")
        print("  5. RL training loop samples expert overrides with higher priority")
        print("  6. TRM agent improves → fewer overrides over time (Agent Score ↑, Override Rate ↓)")
        print()
        print("\nRecommended Demo Flow:")
        print("-" * 70)
        print("  1. Login as 'demo@distdemo.com' (password: Autonomy@2026)")
        print("  2. Lands on Executive Dashboard (SC_VP view)")
        print("  3. Navigate to Planning Cascade > S&OP Policy Envelope")
        print("  4. Walk through layers: SupBP > Supply Worklist > Allocation > Execution")
        print("  5. Navigate to TRM Worklists > ATP Worklist (see TRM decisions)")
        print("  6. Override a decision with reason — show RL feedback loop")
        print("  7. All cascade + TRM pages visible in left nav — no logout needed!")
        print()

    except Exception as e:
        print(f"\nError: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
