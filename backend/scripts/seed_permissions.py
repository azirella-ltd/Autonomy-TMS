#!/usr/bin/env python3
"""
Seed RBAC Permissions

Seeds the database with all 59 granular permissions for capability-based access control.
Run this script after database initialization to set up the permission system.

Usage:
    python scripts/seed_permissions.py
"""

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy.orm import Session, sessionmaker
from app.db.session import sync_engine
from app.services.rbac_service import seed_default_permissions


def main():
    """Seed permissions in the database."""
    print("=" * 60)
    print("Seeding RBAC Permissions")
    print("=" * 60)

    # Create synchronous database session
    SyncSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=sync_engine
    )
    db: Session = SyncSessionLocal()

    try:
        print("\n📦 Seeding 59 default permissions...")
        seed_default_permissions(db)
        print("✅ Permissions seeded successfully!")

        # Print summary
        from app.models.rbac import Permission
        permission_count = db.query(Permission).count()
        print(f"\n📊 Total permissions in database: {permission_count}")

        # Group by category
        from sqlalchemy import func
        categories = db.query(
            Permission.category,
            func.count(Permission.id)
        ).group_by(Permission.category).all()

        print("\n📋 Permissions by category:")
        for category, count in sorted(categories):
            print(f"  • {category}: {count} permissions")

    except Exception as e:
        print(f"\n❌ Error seeding permissions: {e}")
        db.rollback()
        raise
    finally:
        db.close()

    print("\n" + "=" * 60)
    print("Permission seeding complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
