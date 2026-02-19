#!/usr/bin/env python3
"""
Comprehensive script to fix all Item/ProductSiteConfig imports across the codebase.
This script will systematically replace all references.
"""

import os
import re
from pathlib import Path

# Files to exclude from processing
EXCLUDE_FILES = {
    'compatibility.py',
    'migrate_items_to_products.py',
    'demo_mps_key_materials.py',
    'comprehensive_import_fix.py'
}

def fix_import_line(line: str) -> str:
    """Fix a single import line."""
    original = line

    # Pattern 1: from app.models.supply_chain_config import (..., Item, ...)
    if 'from app.models.supply_chain_config import' in line and 'Item' in line:
        # Remove Item and ProductSiteConfig from the import list
        line = re.sub(r',\s*Item\b', '', line)
        line = re.sub(r'\bItem\s*,', '', line)
        line = re.sub(r',\s*ProductSiteConfig\b', '', line)
        line = re.sub(r'\bProductSiteConfig\s*,', '', line)

        # Clean up empty imports or trailing commas
        line = re.sub(r'\(\s*,', '(', line)
        line = re.sub(r',\s*\)', ')', line)
        line = re.sub(r',\s*,', ',', line)

    return line

def needs_compatibility_import(content: str) -> bool:
    """Check if file needs compatibility import."""
    # Check if file uses Item or ProductSiteConfig after imports
    lines = content.split('\n')
    in_imports = False
    past_imports = False

    for line in lines:
        if line.strip().startswith('from ') or line.strip().startswith('import '):
            in_imports = True
        elif in_imports and line.strip() and not line.strip().startswith('#'):
            if not line.strip().startswith('from ') and not line.strip().startswith('import '):
                past_imports = True

        if past_imports:
            # Check for Item or ProductSiteConfig usage in code
            if re.search(r'\bItem\b', line) or re.search(r'\bProductSiteConfig\b', line):
                return True

    return False

def process_file(filepath: Path) -> bool:
    """Process a single Python file."""
    if filepath.name in EXCLUDE_FILES:
        return False

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        original_content = content
        lines = content.split('\n')
        new_lines = []
        import_section_end = 0
        has_compatibility_import = 'from app.models.compatibility import' in content

        # First pass: fix existing imports
        for i, line in enumerate(lines):
            new_line = fix_import_line(line)
            new_lines.append(new_line)

            # Track end of import section
            if (new_line.strip().startswith('from ') or
                new_line.strip().startswith('import ')) and not new_line.strip().startswith('#'):
                import_section_end = i

        content = '\n'.join(new_lines)

        # Second pass: add compatibility import if needed
        if needs_compatibility_import(content) and not has_compatibility_import:
            lines = content.split('\n')
            # Find a good place to insert (after last model import)
            insert_pos = import_section_end + 1
            for i in range(len(lines)):
                if 'from app.models' in lines[i] and not lines[i].strip().startswith('#'):
                    insert_pos = i + 1

            # Insert compatibility import
            lines.insert(insert_pos, 'from app.models.compatibility import Item, ProductSiteConfig  # Temporary compat')
            content = '\n'.join(lines)

        # Write back if changed
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True

    except Exception as e:
        print(f"Error processing {filepath}: {e}")

    return False

def main():
    """Main processing function."""
    backend_path = Path(__file__).parent.parent

    print("=" * 80)
    print("Comprehensive Item Import Fix")
    print("=" * 80)

    # Find all Python files
    py_files = []
    for root, dirs, files in os.walk(backend_path / 'app'):
        # Skip __pycache__ and other directories
        dirs[:] = [d for d in dirs if not d.startswith('__pycache__')]

        for file in files:
            if file.endswith('.py') and file not in EXCLUDE_FILES:
                py_files.append(Path(root) / file)

    # Also process main.py
    main_py = backend_path / 'main.py'
    if main_py.exists():
        py_files.append(main_py)

    print(f"\nProcessing {len(py_files)} Python files...")

    modified = []
    for filepath in py_files:
        if process_file(filepath):
            rel_path = filepath.relative_to(backend_path)
            modified.append(str(rel_path))
            print(f"  ✓ Modified: {rel_path}")

    print("\n" + "=" * 80)
    print(f"Complete! Modified {len(modified)} files")
    print("=" * 80)

    if modified:
        print("\nModified files:")
        for f in modified[:20]:  # Show first 20
            print(f"  - {f}")
        if len(modified) > 20:
            print(f"  ... and {len(modified) - 20} more")

if __name__ == '__main__':
    main()
