#!/usr/bin/env python3
"""
Seed Food Dist Demo - Powell Framework Aligned Users

Creates a Food Dist customer with users aligned to Powell SDAM levels:

Primary Demo User (recommended for demos):
- demo: Combined user with ALL Powell capabilities (no login/logout needed!)
        Lands on Executive Dashboard, can navigate to all Powell views

Individual Role Users (for testing specific role flows):
- sc_vp: VP of Supply Chain (Strategic/CFA level) → Executive Dashboard
- sop_director: S&OP Director (Tactical/S&OP level) → S&OP Worklist
- mps_manager: MPS/Execution Manager (Operational/TRM level) → Agent Decisions

Usage:
    # Run via docker compose
    docker compose exec backend python scripts/seed_dot_foods_demo.py

    # Or directly with venv
    cd backend && python scripts/seed_dot_foods_demo.py

Demo Flow:
    1. Login as demo@distdemo.com (password: Autonomy@2025)
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
from app.models.user import User, UserTypeEnum, PowellRoleEnum
from app.models.customer import Customer, CustomerMode
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


# =============================================================================
# Food Dist Demo Configuration
# =============================================================================

FOOD_DIST_CUSTOMER_NAME = "Food Dist"
FOOD_DIST_DESCRIPTION = "Food Dist - America's largest food redistributor. Powell Framework demo."
DEFAULT_PASSWORD = os.getenv("AUTONOMY_DEFAULT_PASSWORD", "Autonomy@2025")

# User configurations (Powell-aligned)
DEMO_USERS = [
    {
        "username": "fd_group_admin",
        "email": "admin@distdemo.com",
        "full_name": "Food Dist Admin",
        "user_type": UserTypeEnum.GROUP_ADMIN,
        "is_group_admin": True,
        "powell_role": None,  # Customer admin uses built-in capabilities
        "site_scope": None,  # Full access
        "product_scope": None,  # Full access
    },
    # ==========================================================================
    # DEMO USER: Single user with ALL Powell capabilities (no login/logout needed)
    # Lands on Executive Dashboard, can navigate to all Powell dashboards
    # NOTE: user_type=USER with DEMO_ALL role (NOT GROUP_ADMIN)
    # ==========================================================================
    {
        "username": "demo",
        "email": "demo@distdemo.com",
        "full_name": "Demo User (All Roles)",
        "user_type": UserTypeEnum.USER,  # USER, not GROUP_ADMIN
        "is_group_admin": False,
        "powell_role": "DEMO_ALL",  # Union of SC_VP + SOP_DIRECTOR + MPS_MANAGER capabilities
        "site_scope": None,  # Full access
        "product_scope": None,  # Full access
    },
    # ==========================================================================
    # Individual role users (for testing role-specific flows)
    # ==========================================================================
    {
        "username": "sc_vp",
        "email": "scvp@distdemo.com",
        "full_name": "Sarah Chen (VP Supply Chain)",
        "user_type": UserTypeEnum.USER,
        "is_group_admin": False,
        "powell_role": "SC_VP",
        "site_scope": None,  # Full access (strategic level)
        "product_scope": None,  # Full access (strategic level)
    },
    {
        "username": "sop_director",
        "email": "sopdir@distdemo.com",
        "full_name": "Michael Torres (S&OP Director)",
        "user_type": UserTypeEnum.USER,
        "is_group_admin": False,
        "powell_role": "SOP_DIRECTOR",
        "site_scope": None,  # Full access (for demo; production would restrict)
        "product_scope": ["CATEGORY_Frozen", "CATEGORY_Refrigerated"],  # Product category scope
    },
    {
        "username": "mps_manager",
        "email": "mpsmanager@distdemo.com",
        "full_name": "Jennifer Park (MPS Manager)",
        "user_type": UserTypeEnum.USER,
        "is_group_admin": False,
        "powell_role": "MPS_MANAGER",
        "site_scope": ["REGION_Central", "SITE_DC-Chicago", "SITE_DC-Indianapolis"],  # Site scope
        "product_scope": None,  # Full product access within sites
    },
    # ==========================================================================
    # TRM Specialist Users (subordinate to MPS Manager)
    # Each specialist is the human counterpart of one narrow TRM agent.
    # Overrides + reasons feed back into RL training via trm_replay_buffer.
    # ==========================================================================
    {
        "username": "atp_analyst",
        "email": "atp@distdemo.com",
        "full_name": "David Kim (ATP Analyst)",
        "user_type": UserTypeEnum.USER,
        "is_group_admin": False,
        "powell_role": "ATP_ANALYST",
        "site_scope": ["REGION_Central", "SITE_DC-Chicago"],  # Assigned sites
        "product_scope": None,  # All products at assigned sites
    },
    {
        "username": "rebalancing_analyst",
        "email": "rebalancing@distdemo.com",
        "full_name": "Maria Santos (Rebalancing Analyst)",
        "user_type": UserTypeEnum.USER,
        "is_group_admin": False,
        "powell_role": "REBALANCING_ANALYST",
        "site_scope": ["REGION_Central", "SITE_DC-Chicago", "SITE_DC-Indianapolis"],  # Cross-site scope
        "product_scope": None,  # All products for transfers
    },
    {
        "username": "po_analyst",
        "email": "po@distdemo.com",
        "full_name": "James Wilson (PO Analyst)",
        "user_type": UserTypeEnum.USER,
        "is_group_admin": False,
        "powell_role": "PO_ANALYST",
        "site_scope": ["SITE_DC-Chicago"],  # Single site focus
        "product_scope": ["CATEGORY_Frozen", "CATEGORY_Refrigerated"],  # Product category scope
    },
    {
        "username": "order_tracking_analyst",
        "email": "ordertracking@distdemo.com",
        "full_name": "Lisa Chen (Order Tracking Analyst)",
        "user_type": UserTypeEnum.USER,
        "is_group_admin": False,
        "powell_role": "ORDER_TRACKING_ANALYST",
        "site_scope": None,  # All sites (exceptions can come from anywhere)
        "product_scope": None,  # All products
    },
]

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
    customer_id: int,
    powell_role: PowellRoleEnum = None,
    site_scope: list = None,
    product_scope: list = None,
) -> User:
    """Create a user or update existing one with correct attributes.

    Args:
        powell_role: Powell Framework role that determines landing page.
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
        if existing.powell_role != powell_role:
            old_role = existing.powell_role.value if existing.powell_role else None
            new_role = powell_role.value if powell_role else None
            print(f"  Updating user '{username}' powell_role: {old_role} -> {new_role}")
            existing.powell_role = powell_role
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
        if customer_id and existing.customer_id != customer_id:
            existing.customer_id = customer_id
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
        customer_id=customer_id,
        powell_role=powell_role,
        is_active=True,
        is_superuser=False,
        site_scope=site_scope,
        product_scope=product_scope,
    )
    db.add(user)
    db.flush()
    powell_str = powell_role.value if powell_role else "None"
    print(f"  Created user '{username}' (id={user.id}, type={user_type.value}, powell_role={powell_str})")
    return user


def create_or_get_customer(db: Session, admin_user: User) -> Customer:
    """Create Food Dist customer or return existing one."""
    existing = db.query(Customer).filter(Customer.name == FOOD_DIST_CUSTOMER_NAME).first()
    if existing:
        print(f"Customer '{FOOD_DIST_CUSTOMER_NAME}' already exists (id={existing.id})")
        return existing

    customer = Customer(
        name=FOOD_DIST_CUSTOMER_NAME,
        description=FOOD_DIST_DESCRIPTION,
        admin_id=admin_user.id,
        mode=CustomerMode.PRODUCTION,  # Operational customer
    )
    db.add(customer)
    db.flush()
    print(f"Created customer '{FOOD_DIST_CUSTOMER_NAME}' (id={customer.id})")
    return customer


def create_powell_role(
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


def _generate_sc_config_for_group(customer_id: int):
    """Generate Food Dist SC config for an existing customer using async generator."""
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
                    existing_customer_id=customer_id,
                )
                config_id = result.get("config_id")
                status = result.get("summary", {}).get("status")
                if status == "already_exists":
                    print(f"  SC config already exists for customer {customer_id} (config_id={config_id})")
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

        # Step 2: Create customer admin user first (needed for customer creation)
        print("\n2. Creating customer admin user...")
        admin_config = next(u for u in DEMO_USERS if u["is_group_admin"])
        admin_user = create_or_get_user(
            db=db,
            username=admin_config["username"],
            email=admin_config["email"],
            full_name=admin_config["full_name"],
            user_type=admin_config["user_type"],
            customer_id=None,  # Will be updated after customer creation
        )
        db.commit()

        # Step 3: Create Food Dist customer
        print("\n3. Creating Food Dist customer...")
        customer = create_or_get_customer(db, admin_user)

        # Update admin user's customer_id
        admin_user.customer_id = customer.id
        db.commit()

        # Step 4: Create RBAC service and Powell roles
        print("\n4. Creating Powell-aligned RBAC roles...")
        rbac_service = RBACService(db)

        powell_roles = {}
        for role_name in POWELL_ROLE_CAPABILITIES.keys():
            role = create_powell_role(db, rbac_service, role_name, customer_id=customer.id)
            powell_roles[role_name] = role

        db.commit()

        # Step 5: Create other users and assign roles
        print("\n5. Creating Powell-aligned users...")
        for user_config in DEMO_USERS:
            if user_config["is_group_admin"]:
                continue  # Already created

            # Convert powell_role string to enum (if specified)
            powell_role_str = user_config.get("powell_role")
            powell_role_enum = None
            if powell_role_str:
                try:
                    powell_role_enum = PowellRoleEnum(powell_role_str)
                except ValueError:
                    print(f"  Warning: Unknown powell_role '{powell_role_str}', skipping")

            user = create_or_get_user(
                db=db,
                username=user_config["username"],
                email=user_config["email"],
                full_name=user_config["full_name"],
                user_type=user_config["user_type"],
                customer_id=customer.id,
                powell_role=powell_role_enum,  # Store on user for landing page routing
                site_scope=user_config.get("site_scope"),
                product_scope=user_config.get("product_scope"),
            )

            # Assign RBAC role for capabilities (can be customized by customer admin)
            if powell_role_str:
                role = powell_roles.get(powell_role_str)
                if role and role not in user.roles:
                    user.roles.append(role)
                    print(f"    Assigned RBAC role '{role.name}' to '{user.username}'")

        db.commit()

        # Step 6: Generate Food Dist SC config for this customer (async)
        print("\n6. Generating Food Dist supply chain config for customer...")
        _generate_sc_config_for_group(customer.id)

        # Step 7: Print summary
        print("\n" + "=" * 70)
        print("Food Dist Demo Setup Complete!")
        print("=" * 70)
        print(f"\nCustomer: {FOOD_DIST_CUSTOMER_NAME} (ID: {customer.id})")
        print(f"Mode: {customer.mode.value}")
        print(f"\nUsers created (password: {DEFAULT_PASSWORD}):")
        print("-" * 50)

        for user_config in DEMO_USERS:
            powell_role = user_config.get("powell_role", "GROUP_ADMIN")
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
            }.get(powell_role, "Unknown")

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
        print("  sop_director         -> Tactical: MRS candidates (L2), Supply/Allocation (L3-L4)")
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
        print("  1. Login as 'demo@distdemo.com' (password: Autonomy@2025)")
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
