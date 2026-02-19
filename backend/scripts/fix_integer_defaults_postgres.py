#!/usr/bin/env python3
"""
Fix PostgreSQL integer defaults in migration files.

This script fixes integer fields that were incorrectly set to FALSE instead of 0.
"""

import os
import re
from pathlib import Path

def fix_integer_defaults(file_path):
    """Fix integer defaults in a single migration file."""
    with open(file_path, 'r') as f:
        content = f.read()

    original_content = content
    changes_made = []

    # Pattern: sa.Integer() fields with server_default=sa.text("FALSE") -> should be "0"
    pattern1 = r'(sa\.Integer\(\).*?server_default=sa\.text\()"FALSE"(\))'
    matches = re.findall(pattern1, content)
    if matches:
        content = re.sub(pattern1, r'\g<1>"0"\g<2>', content)
        changes_made.append(f"Fixed {len(matches)} Integer fields: FALSE -> 0")

    # Pattern: sa.Integer() fields with server_default=sa.text("TRUE") -> should be "1"
    pattern2 = r'(sa\.Integer\(\).*?server_default=sa\.text\()"TRUE"(\))'
    matches2 = re.findall(pattern2, content)
    if matches2:
        content = re.sub(pattern2, r'\g<1>"1"\g<2>', content)
        changes_made.append(f"Fixed {len(matches2)} Integer fields: TRUE -> 1")

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
    print("Fixing PostgreSQL Integer Defaults in Migrations")
    print("=" * 80)
    print(f"\nScanning: {migrations_dir}\n")

    fixed_files = []
    total_files = 0

    for migration_file in sorted(migrations_dir.glob('*.py')):
        if migration_file.name == '__init__.py':
            continue

        total_files += 1
        changed, changes = fix_integer_defaults(migration_file)

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
            print(f"  - {filename}")
            for change in changes:
                print(f"    {change}")


if __name__ == "__main__":
    main()
