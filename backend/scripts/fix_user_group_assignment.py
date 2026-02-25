#!/usr/bin/env python3
"""Fix user-customer assignments by ensuring all users have a customer_id."""

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
from app.models.customer import Customer

def main():
    # Create database connection
    engine = create_engine(settings.SQLALCHEMY_DATABASE_URI, echo=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with SessionLocal() as db:
        # Get all users
        users = db.execute(select(User)).scalars().all()

        print("\n=== User Status ===")
        for user in users:
            customer = db.execute(select(Customer).where(Customer.id == user.customer_id)).scalars().first() if user.customer_id else None
            print(f"User: {user.email} ({user.username})")
            print(f"  ID: {user.id}")
            print(f"  User Type: {user.user_type}")
            print(f"  Customer ID: {user.customer_id}")
            print(f"  Customer: {customer.name if customer else 'NONE'}")
            print()

        # Get all customers
        customers = db.execute(select(Customer)).scalars().all()

        print("\n=== Customers ===")
        for customer in customers:
            admin = db.execute(select(User).where(User.id == customer.admin_id)).scalars().first() if customer.admin_id else None
            print(f"Customer: {customer.name}")
            print(f"  ID: {customer.id}")
            print(f"  Admin ID: {customer.admin_id}")
            print(f"  Admin: {admin.email if admin else 'NONE'}")

            # Count users in this customer
            users_in_customer = db.execute(
                select(User).where(User.customer_id == customer.id)
            ).scalars().all()
            print(f"  Users in customer: {len(users_in_customer)}")
            for u in users_in_customer:
                print(f"    - {u.email} ({u.user_type})")
            print()

        # Fix orphaned users (users without a customer)
        orphaned = db.execute(
            select(User).where(User.customer_id.is_(None))
        ).scalars().all()

        if orphaned:
            print("\n=== Fixing Orphaned Users ===")

            # Get or create default customer
            default_customer = db.execute(
                select(Customer).where(Customer.name == "Beer Game")
            ).scalars().first()

            if not default_customer:
                # Try Autonomy customer
                default_customer = db.execute(
                    select(Customer).where(Customer.name == "Autonomy")
                ).scalars().first()

            if not default_customer:
                print("ERROR: No default customer found! Creating default customer...")
                # Get first user to be admin
                first_user = users[0] if users else None
                if not first_user:
                    print("ERROR: No users found! Cannot create customer.")
                    return

                default_customer = Customer(
                    name="Beer Game",
                    description="Default simulation customer",
                    admin_id=first_user.id
                )
                db.add(default_customer)
                db.flush()
                print(f"Created default customer with ID {default_customer.id}")

            for user in orphaned:
                print(f"Assigning {user.email} to customer '{default_customer.name}' (ID: {default_customer.id})")
                user.customer_id = default_customer.id
                db.add(user)

            db.commit()
            print(f"Fixed {len(orphaned)} orphaned users")
        else:
            print("\n✅ No orphaned users found - all users are assigned to customers")

        # Verify customer admin assignments
        print("\n=== Verifying Customer Admin Assignments ===")
        for customer in customers:
            if customer.admin_id:
                admin = db.execute(select(User).where(User.id == customer.admin_id)).scalars().first()
                if admin and admin.customer_id != customer.id:
                    print(f"⚠️  Customer '{customer.name}' admin '{admin.email}' is in wrong customer!")
                    print(f"   Admin's customer_id: {admin.customer_id}, Expected: {customer.id}")
                    print(f"   Fixing...")
                    admin.customer_id = customer.id
                    db.add(admin)
                    db.commit()
                    print(f"   ✅ Fixed!")
                elif admin:
                    print(f"✅ Customer '{customer.name}' admin '{admin.email}' correctly assigned")

if __name__ == "__main__":
    main()
