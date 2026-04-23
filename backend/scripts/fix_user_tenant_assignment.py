#!/usr/bin/env python3
"""Fix user-tenant assignments by ensuring all users have a tenant_id."""

import sys
from pathlib import Path

# Add backend to path
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.append(str(BACKEND_ROOT))

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models.user import User
from app.models.tenant import Tenant

def main():
    # Create database connection
    engine = create_engine(settings.SQLALCHEMY_DATABASE_URI, echo=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with SessionLocal() as db:
        # Get all users
        users = db.execute(select(User)).scalars().all()

        print("\n=== User Status ===")
        for user in users:
            tenant = db.execute(select(Tenant).where(Tenant.id == user.tenant_id)).scalars().first() if user.tenant_id else None
            print(f"User: {user.email} ({user.username})")
            print(f"  ID: {user.id}")
            print(f"  User Type: {user.user_type}")
            print(f"  Tenant ID: {user.tenant_id}")
            print(f"  Tenant: {tenant.name if tenant else 'NONE'}")
            print()

        # Get all tenants
        tenants = db.execute(select(Tenant)).scalars().all()

        print("\n=== Tenants ===")
        for tenant in tenants:
            admin = db.execute(select(User).where(User.id == tenant.admin_id)).scalars().first() if tenant.admin_id else None
            print(f"Tenant: {tenant.name}")
            print(f"  ID: {tenant.id}")
            print(f"  Admin ID: {tenant.admin_id}")
            print(f"  Admin: {admin.email if admin else 'NONE'}")

            # Count users in this tenant
            users_in_tenant = db.execute(
                select(User).where(User.tenant_id == tenant.id)
            ).scalars().all()
            print(f"  Users in tenant: {len(users_in_tenant)}")
            for u in users_in_tenant:
                print(f"    - {u.email} ({u.user_type})")
            print()

        # Fix orphaned users (users without a tenant)
        orphaned = db.execute(
            select(User).where(User.tenant_id.is_(None))
        ).scalars().all()

        if orphaned:
            print("\n=== Fixing Orphaned Users ===")

            # Get or create default tenant
            default_tenant = db.execute(
                select(Tenant).where(Tenant.name == "Beer Scenario")
            ).scalars().first()

            if not default_tenant:
                # Try Autonomy tenant
                default_tenant = db.execute(
                    select(Tenant).where(Tenant.name == "Autonomy")
                ).scalars().first()

            if not default_tenant:
                print("ERROR: No default tenant found! Creating default tenant...")
                # Get first user to be admin
                first_user = users[0] if users else None
                if not first_user:
                    print("ERROR: No users found! Cannot create tenant.")
                    return

                default_tenant = Tenant(
                    name="Beer Scenario",
                    description="Default simulation tenant",
                    admin_id=first_user.id
                )
                db.add(default_tenant)
                db.flush()
                print(f"Created default tenant with ID {default_tenant.id}")

            for user in orphaned:
                print(f"Assigning {user.email} to tenant '{default_tenant.name}' (ID: {default_tenant.id})")
                user.tenant_id = default_tenant.id
                db.add(user)

            db.commit()
            print(f"Fixed {len(orphaned)} orphaned users")
        else:
            print("\n✅ No orphaned users found - all users are assigned to tenants")

        # Verify tenant admin assignments
        print("\n=== Verifying Tenant Admin Assignments ===")
        for tenant in tenants:
            if tenant.admin_id:
                admin = db.execute(select(User).where(User.id == tenant.admin_id)).scalars().first()
                if admin and admin.tenant_id != tenant.id:
                    print(f"⚠️  Tenant '{tenant.name}' admin '{admin.email}' is in wrong tenant!")
                    print(f"   Admin's tenant_id: {admin.tenant_id}, Expected: {tenant.id}")
                    print(f"   Fixing...")
                    admin.tenant_id = tenant.id
                    db.add(admin)
                    db.commit()
                    print(f"   ✅ Fixed!")
                elif admin:
                    print(f"✅ Tenant '{tenant.name}' admin '{admin.email}' correctly assigned")

if __name__ == "__main__":
    main()
