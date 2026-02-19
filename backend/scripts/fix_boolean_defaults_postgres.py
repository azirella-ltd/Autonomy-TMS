#!/usr/bin/env python3
"""
Fix PostgreSQL boolean defaults in migration files.

This script replaces MariaDB-style boolean defaults (0/1) with PostgreSQL-style (TRUE/FALSE).
"""

import os
import re
from pathlib import Path

def fix_boolean_defaults(file_path):
    """Fix boolean defaults in a single migration file."""
    with open(file_path, 'r') as f:
        content = f.read()

    original_content = content
    changes_made = []

    # Pattern 1: server_default=sa.text("0") -> server_default=sa.text("FALSE")
    pattern1 = r'server_default=sa\.text\("0"\)'
    if re.search(pattern1, content):
        content = re.sub(pattern1, 'server_default=sa.text("FALSE")', content)
        changes_made.append("0 -> FALSE")

    # Pattern 2: server_default=sa.text("1") -> server_default=sa.text("TRUE")
    pattern2 = r'server_default=sa\.text\("1"\)'
    if re.search(pattern2, content):
        content = re.sub(pattern2, 'server_default=sa.text("TRUE")', content)
        changes_made.append("1 -> TRUE")

    # Pattern 3: server_default="0" -> server_default=sa.text("FALSE")
    pattern3 = r'server_default="0"'
    if re.search(pattern3, content):
        content = re.sub(pattern3, 'server_default=sa.text("FALSE")', content)
        changes_made.append('"0" -> FALSE')

    # Pattern 4: server_default="1" -> server_default=sa.text("TRUE")
    pattern4 = r'server_default="1"'
    if re.search(pattern4, content):
        content = re.sub(pattern4, 'server_default=sa.text("TRUE")', content)
        changes_made.append('"1" -> TRUE')

    # Pattern 5: server_default='0' -> server_default=sa.text("FALSE")
    pattern5 = r"server_default='0'"
    if re.search(pattern5, content):
        content = re.sub(pattern5, 'server_default=sa.text("FALSE")', content)
        changes_made.append("'0' -> FALSE")

    # Pattern 6: server_default='1' -> server_default=sa.text("TRUE")
    pattern6 = r"server_default='1'"
    if re.search(pattern6, content):
        content = re.sub(pattern6, 'server_default=sa.text("TRUE")', content)
        changes_made.append("'1' -> TRUE")

    # Pattern 7: sa.text('0') -> sa.text("FALSE")
    pattern7 = r"sa\.text\('0'\)"
    if re.search(pattern7, content):
        content = re.sub(pattern7, 'sa.text("FALSE")', content)
        changes_made.append("text('0') -> FALSE")

    # Pattern 8: sa.text('1') -> sa.text("TRUE")
    pattern8 = r"sa\.text\('1'\)"
    if re.search(pattern8, content):
        content = re.sub(pattern8, 'sa.text("TRUE")', content)
        changes_made.append("text('1') -> TRUE")

    if content != original_content:
        with open(file_path, 'w') as f:
            f.write(content)
        return True, changes_made

    return False, []


def main():
    """Fix all migration files."""
    migrations_dir = Path(__file__).parent.parent / 'migrations' / 'versions'

    if not migrations_dir.exists():
        print(f"Error: Migrations directory not found: {migrations_dir}")
        return

    print("=" * 80)
    print("Fixing PostgreSQL Boolean Defaults in Migrations")
    print("=" * 80)
    print(f"\nScanning: {migrations_dir}\n")

    fixed_files = []
    total_files = 0

    for migration_file in sorted(migrations_dir.glob('*.py')):
        if migration_file.name == '__init__.py':
            continue

        total_files += 1
        changed, changes = fix_boolean_defaults(migration_file)

        if changed:
            fixed_files.append((migration_file.name, changes))
            print(f"✓ Fixed: {migration_file.name}")
            for change in changes:
                print(f"  - {change}")
        else:
            print(f"  {migration_file.name} - OK")

    print("\n" + "=" * 80)
    print(f"Summary: Fixed {len(fixed_files)} of {total_files} migration files")
    print("=" * 80)

    if fixed_files:
        print("\nFixed files:")
        for filename, changes in fixed_files:
            print(f"  - {filename}: {', '.join(changes)}")


if __name__ == "__main__":
    main()
