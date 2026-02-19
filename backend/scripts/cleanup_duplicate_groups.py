#!/usr/bin/env python3
"""
Cleanup Duplicate Groups and Configs

This script:
1. Removes duplicate groups (keeps Food Dist production + Food Dist Training)
2. Removes duplicate configs
3. Fixes configs that shouldn't be in production groups (like Default Beer Game)

Run with:
    docker compose exec backend python scripts/cleanup_duplicate_groups.py
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal


def cleanup_duplicates():
    """Clean up duplicate groups and configs."""
    db = SessionLocal()

    try:
        print("=" * 60)
        print("CLEANUP: Duplicate Groups and Configs")
        print("=" * 60)

        # 1. List current state
        print("\n--- Current Groups ---")
        result = db.execute(text("""
            SELECT g.id, g.name, g.mode, COUNT(c.id) as config_count
            FROM groups g
            LEFT JOIN supply_chain_configs c ON c.group_id = g.id
            GROUP BY g.id, g.name, g.mode
            ORDER BY g.id
        """))
        for row in result:
            print(f"  Group {row.id}: {row.name} ({row.mode}) - {row.config_count} configs")

        # 2. Remove duplicate "Default Beer Game" from Group 1 (keep id=1, remove id=20)
        print("\n--- Removing duplicate Default Beer Game (id=20) from Group 1 ---")
        result = db.execute(text("""
            DELETE FROM supply_chain_configs WHERE id = 20 AND name = 'Default Beer Game'
            RETURNING id, name
        """))
        deleted = result.fetchall()
        if deleted:
            print(f"  Deleted: {deleted}")
        else:
            print("  No duplicate Default Beer Game found (id=20)")

        # 3. Remove "Default Beer Game" from production group 13 (shouldn't have TBG configs)
        print("\n--- Removing Default Beer Game from production group (id=13) ---")
        result = db.execute(text("""
            DELETE FROM supply_chain_configs
            WHERE group_id = 13 AND name = 'Default Beer Game'
            RETURNING id, name
        """))
        deleted = result.fetchall()
        if deleted:
            print(f"  Deleted: {deleted}")
        else:
            print("  No Default Beer Game found in group 13")

        # 4. Check if Group 9 "Food Dist" should be merged or deleted
        # It has one config and one user - let's reassign to Group 12 (Training)
        print("\n--- Migrating Group 9 (Food Dist) to Group 12 (Food Dist Training) ---")

        # Move configs from Group 9 to Group 12
        result = db.execute(text("""
            UPDATE supply_chain_configs
            SET group_id = 12
            WHERE group_id = 9
            RETURNING id, name
        """))
        moved_configs = result.fetchall()
        if moved_configs:
            print(f"  Moved configs to Group 12: {moved_configs}")

        # Move users from Group 9 to Group 12
        result = db.execute(text("""
            UPDATE users
            SET group_id = 12
            WHERE group_id = 9
            RETURNING id, email
        """))
        moved_users = result.fetchall()
        if moved_users:
            print(f"  Moved users to Group 12: {moved_users}")

        # Delete Group 9
        result = db.execute(text("""
            DELETE FROM groups WHERE id = 9
            RETURNING id, name
        """))
        deleted_group = result.fetchall()
        if deleted_group:
            print(f"  Deleted group: {deleted_group}")

        # 5. Rename Group 12 to "Food Dist Learning" for clarity
        print("\n--- Renaming Group 12 to 'Food Dist Learning' ---")
        db.execute(text("""
            UPDATE groups SET name = 'Food Dist Learning' WHERE id = 12
        """))
        print("  Renamed Group 12 to 'Food Dist Learning'")

        db.commit()

        # 6. Show final state
        print("\n--- Final State ---")
        print("\nGroups:")
        result = db.execute(text("""
            SELECT g.id, g.name, g.mode, COUNT(c.id) as config_count
            FROM groups g
            LEFT JOIN supply_chain_configs c ON c.group_id = g.id
            GROUP BY g.id, g.name, g.mode
            ORDER BY g.id
        """))
        for row in result:
            print(f"  Group {row.id}: {row.name} ({row.mode}) - {row.config_count} configs")

        print("\nConfigs:")
        result = db.execute(text("""
            SELECT c.id, c.name, g.name as group_name, g.mode
            FROM supply_chain_configs c
            JOIN groups g ON c.group_id = g.id
            ORDER BY g.id, c.id
        """))
        for row in result:
            print(f"  Config {row.id}: {row.name} -> {row.group_name} ({row.mode})")

        print("\n" + "=" * 60)
        print("CLEANUP COMPLETE")
        print("=" * 60)

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    cleanup_duplicates()
