#!/usr/bin/env python3
"""Fix user-group assignments by ensuring all users have a group_id."""

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
from app.models.group import Group

def main():
    # Create database connection
    engine = create_engine(settings.SQLALCHEMY_DATABASE_URI, echo=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with SessionLocal() as db:
        # Get all users
        users = db.execute(select(User)).scalars().all()

        print("\n=== User Status ===")
        for user in users:
            group = db.execute(select(Group).where(Group.id == user.group_id)).scalars().first() if user.group_id else None
            print(f"User: {user.email} ({user.username})")
            print(f"  ID: {user.id}")
            print(f"  User Type: {user.user_type}")
            print(f"  Group ID: {user.group_id}")
            print(f"  Group: {group.name if group else 'NONE'}")
            print()

        # Get all groups
        groups = db.execute(select(Group)).scalars().all()

        print("\n=== Groups ===")
        for group in groups:
            admin = db.execute(select(User).where(User.id == group.admin_id)).scalars().first() if group.admin_id else None
            print(f"Group: {group.name}")
            print(f"  ID: {group.id}")
            print(f"  Admin ID: {group.admin_id}")
            print(f"  Admin: {admin.email if admin else 'NONE'}")

            # Count users in this group
            users_in_group = db.execute(
                select(User).where(User.group_id == group.id)
            ).scalars().all()
            print(f"  Users in group: {len(users_in_group)}")
            for u in users_in_group:
                print(f"    - {u.email} ({u.user_type})")
            print()

        # Fix orphaned users (users without a group)
        orphaned = db.execute(
            select(User).where(User.group_id.is_(None))
        ).scalars().all()

        if orphaned:
            print("\n=== Fixing Orphaned Users ===")

            # Get or create default group
            default_group = db.execute(
                select(Group).where(Group.name == "Beer Game")
            ).scalars().first()

            if not default_group:
                # Try Autonomy group
                default_group = db.execute(
                    select(Group).where(Group.name == "Autonomy")
                ).scalars().first()

            if not default_group:
                print("ERROR: No default group found! Creating Beer Game group...")
                # Get first user to be admin
                first_user = users[0] if users else None
                if not first_user:
                    print("ERROR: No users found! Cannot create group.")
                    return

                default_group = Group(
                    name="Beer Game",
                    description="Default Beer Game group",
                    admin_id=first_user.id
                )
                db.add(default_group)
                db.flush()
                print(f"Created Beer Game group with ID {default_group.id}")

            for user in orphaned:
                print(f"Assigning {user.email} to group '{default_group.name}' (ID: {default_group.id})")
                user.group_id = default_group.id
                db.add(user)

            db.commit()
            print(f"Fixed {len(orphaned)} orphaned users")
        else:
            print("\n✅ No orphaned users found - all users are assigned to groups")

        # Verify group admin assignments
        print("\n=== Verifying Group Admin Assignments ===")
        for group in groups:
            if group.admin_id:
                admin = db.execute(select(User).where(User.id == group.admin_id)).scalars().first()
                if admin and admin.group_id != group.id:
                    print(f"⚠️  Group '{group.name}' admin '{admin.email}' is in wrong group!")
                    print(f"   Admin's group_id: {admin.group_id}, Expected: {group.id}")
                    print(f"   Fixing...")
                    admin.group_id = group.id
                    db.add(admin)
                    db.commit()
                    print(f"   ✅ Fixed!")
                elif admin:
                    print(f"✅ Group '{group.name}' admin '{admin.email}' correctly assigned")

if __name__ == "__main__":
    main()
