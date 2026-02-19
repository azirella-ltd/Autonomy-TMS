#!/bin/bash
# AWS Field Rename Automation Script
# Phase 2: Breaking Changes - Field Name Alignment
#
# ⚠️  CRITICAL: This script makes BREAKING CHANGES
# ⚠️  Test thoroughly before running on production code
# ⚠️  Create a git branch first: git checkout -b feature/aws-field-renames

set -e  # Exit on error

BACKEND_DIR="backend/app"
FRONTEND_DIR="frontend/src"
DRY_RUN=${DRY_RUN:-1}  # Default to dry run

echo "=============================================="
echo "AWS Supply Chain Field Rename Script"
echo "=============================================="
echo ""
echo "This script will rename fields to AWS standards:"
echo "  • item_id       → product_id"
echo "  • node_id       → site_id"
echo "  • upstream_node_id   → from_site_id"
echo "  • downstream_node_id → to_site_id"
echo ""

if [ "$DRY_RUN" = "1" ]; then
    echo "🔍 DRY RUN MODE - No changes will be made"
    echo "   Set DRY_RUN=0 to apply changes"
else
    echo "⚠️  LIVE MODE - Changes will be applied!"
    read -p "Are you sure? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Aborted."
        exit 1
    fi
fi

echo ""
echo "=============================================="

# Function to perform rename with dry-run support
rename_field() {
    local old_pattern="$1"
    local new_pattern="$2"
    local file_pattern="$3"
    local description="$4"

    echo ""
    echo "Processing: $description"
    echo "  Pattern: $old_pattern → $new_pattern"
    echo "  Files: $file_pattern"

    if [ "$DRY_RUN" = "1" ]; then
        # Count occurrences
        count=$(find $file_pattern -type f 2>/dev/null | xargs grep -l "$old_pattern" 2>/dev/null | wc -l)
        echo "  Found in: $count files"

        # Show sample matches
        echo "  Sample matches:"
        find $file_pattern -type f 2>/dev/null | xargs grep -n "$old_pattern" 2>/dev/null | head -5 | sed 's/^/    /'
    else
        # Apply changes
        find $file_pattern -type f -exec sed -i.bak \
            -e "s/$old_pattern/$new_pattern/g" \
            {} +
        echo "  ✅ Applied"
    fi
}

# =============================================================================
# BACKEND PYTHON FILES
# =============================================================================

echo ""
echo "========== BACKEND: Python Field Renames =========="

# 1. Item ID → Product ID (most common)
rename_field \
    '\bitem_id\b' \
    'product_id' \
    "$BACKEND_DIR -name '*.py'" \
    "item_id → product_id (Python)"

# 2. Node ID → Site ID
rename_field \
    '\bnode_id\b' \
    'site_id' \
    "$BACKEND_DIR -name '*.py'" \
    "node_id → site_id (Python)"

# 3. Upstream Node ID → From Site ID
rename_field \
    '\bupstream_node_id\b' \
    'from_site_id' \
    "$BACKEND_DIR -name '*.py'" \
    "upstream_node_id → from_site_id (Python)"

# 4. Downstream Node ID → To Site ID
rename_field \
    '\bdownstream_node_id\b' \
    'to_site_id' \
    "$BACKEND_DIR -name '*.py'" \
    "downstream_node_id → to_site_id (Python)"

# 5. Supplier Node ID → Supplier Site ID
rename_field \
    '\bsupplier_node_id\b' \
    'supplier_site_id' \
    "$BACKEND_DIR -name '*.py'" \
    "supplier_node_id → supplier_site_id (Python)"

# 6. from_node / to_node in orders → from_site / to_site
rename_field \
    '\bfrom_node\b' \
    'from_site' \
    "$BACKEND_DIR -name '*.py'" \
    "from_node → from_site (Python)"

rename_field \
    '\bto_node\b' \
    'to_site' \
    "$BACKEND_DIR -name '*.py'" \
    "to_node → to_site (Python)"

# 7. node_key → site_key (players)
rename_field \
    '\bnode_key\b' \
    'site_key' \
    "$BACKEND_DIR -name '*.py'" \
    "node_key → site_key (Python)"

# =============================================================================
# FRONTEND JAVASCRIPT/JSX FILES
# =============================================================================

echo ""
echo "========== FRONTEND: JavaScript Field Renames =========="

# 1. item_id → product_id (snake_case)
rename_field \
    '\bitem_id\b' \
    'product_id' \
    "$FRONTEND_DIR -name '*.js' -o -name '*.jsx'" \
    "item_id → product_id (JS/JSX)"

# 2. itemId → productId (camelCase)
rename_field \
    '\bitemId\b' \
    'productId' \
    "$FRONTEND_DIR -name '*.js' -o -name '*.jsx'" \
    "itemId → productId (JS/JSX camelCase)"

# 3. node_id → site_id (snake_case)
rename_field \
    '\bnode_id\b' \
    'site_id' \
    "$FRONTEND_DIR -name '*.js' -o -name '*.jsx'" \
    "node_id → site_id (JS/JSX)"

# 4. nodeId → siteId (camelCase)
rename_field \
    '\bnodeId\b' \
    'siteId' \
    "$FRONTEND_DIR -name '*.js' -o -name '*.jsx'" \
    "nodeId → siteId (JS/JSX camelCase)"

# 5. upstream_node_id → from_site_id
rename_field \
    '\bupstream_node_id\b' \
    'from_site_id' \
    "$FRONTEND_DIR -name '*.js' -o -name '*.jsx'" \
    "upstream_node_id → from_site_id (JS/JSX)"

# 6. upstreamNodeId → fromSiteId (camelCase)
rename_field \
    '\bupstreamNodeId\b' \
    'fromSiteId' \
    "$FRONTEND_DIR -name '*.js' -o -name '*.jsx'" \
    "upstreamNodeId → fromSiteId (JS/JSX camelCase)"

# 7. downstream_node_id → to_site_id
rename_field \
    '\bdownstream_node_id\b' \
    'to_site_id' \
    "$FRONTEND_DIR -name '*.js' -o -name '*.jsx'" \
    "downstream_node_id → to_site_id (JS/JSX)"

# 8. downstreamNodeId → toSiteId (camelCase)
rename_field \
    '\bdownstreamNodeId\b' \
    'toSiteId' \
    "$FRONTEND_DIR -name '*.js' -o -name '*.jsx'" \
    "downstreamNodeId → toSiteId (JS/JSX camelCase)"

# 9. from_node / to_node
rename_field \
    '\bfromNode\b' \
    'fromSite' \
    "$FRONTEND_DIR -name '*.js' -o -name '*.jsx'" \
    "fromNode → fromSite (JS/JSX)"

rename_field \
    '\btoNode\b' \
    'toSite' \
    "$FRONTEND_DIR -name '*.js' -o -name '*.jsx'" \
    "toNode → toSite (JS/JSX)"

# =============================================================================
# SUMMARY
# =============================================================================

echo ""
echo "=============================================="
echo "Script Complete!"
echo "=============================================="

if [ "$DRY_RUN" = "1" ]; then
    echo ""
    echo "✅ Dry run complete - no changes made"
    echo ""
    echo "To apply changes:"
    echo "  1. Create a git branch: git checkout -b feature/aws-field-renames"
    echo "  2. Run: DRY_RUN=0 ./scripts/aws_field_rename.sh"
    echo "  3. Review changes: git diff"
    echo "  4. Run tests"
    echo "  5. Commit if all passes"
else
    echo ""
    echo "✅ Changes applied!"
    echo ""
    echo "Next steps:"
    echo "  1. Review changes: git diff"
    echo "  2. Check for any .bak files: find . -name '*.bak'"
    echo "  3. Run tests to verify"
    echo "  4. Commit changes"
    echo "  5. Run the database migration"
fi

echo ""
echo "⚠️  IMPORTANT:"
echo "  • This is an automated script - manual review REQUIRED"
echo "  • Some contexts may need special handling"
echo "  • Test thoroughly before deploying"
echo "  • Keep .bak files until verified"
echo ""
