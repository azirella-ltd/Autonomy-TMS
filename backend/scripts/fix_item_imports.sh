#!/bin/bash
# Script to replace Item imports with Product imports throughout the codebase

echo "Fixing Item imports across the codebase..."

# Find all Python files that import Item
FILES=$(grep -rl "from.*supply_chain_config.*import.*Item" backend/app --include="*.py")

for file in $FILES; do
    echo "Processing $file..."

    # Replace "Item" with "Product" in imports from supply_chain_config
    sed -i 's/from app\.models\.supply_chain_config import \(.*\)Item\(.*\)/from app.models.supply_chain_config import \1\2\nfrom app.models.sc_entities import Product/g' "$file"

    # Clean up the import line (remove Item references)
    sed -i '/from app\.models\.supply_chain_config import/s/, Item//g' "$file"
    sed -i '/from app\.models\.supply_chain_config import/s/Item, //g' "$file"
    sed -i '/from app\.models\.supply_chain_config import/s/Item//g' "$file"

    # Also remove ItemNodeConfig and ItemNodeSupplier if present
    sed -i '/from app\.models\.supply_chain_config import/s/, ItemNodeConfig//g' "$file"
    sed -i '/from app\.models\.supply_chain_config import/s/ItemNodeConfig, //g' "$file"
    sed -i '/from app\.models\.supply_chain_config import/s/, ItemNodeSupplier//g' "$file"
    sed -i '/from app\.models\.supply_chain_config import/s/ItemNodeSupplier, //g' "$file"

    echo "  ✓ Updated $file"
done

echo ""
echo "Now searching for db.query(Item) and similar direct usages..."

# Find files that use Item class directly (not just imports)
FILES_WITH_ITEM_USAGE=$(grep -rl "db\.query(Item)" backend/app --include="*.py")
FILES_WITH_ITEM_USAGE+=$(grep -rl "db\.get(Item" backend/app --include="*.py")

for file in $FILES_WITH_ITEM_USAGE; do
    echo "Replacing Item class usage in $file..."

    # Replace db.query(Item) with db.query(Product)
    sed -i 's/db\.query(Item)/db.query(Product)/g' "$file"

    # Replace db.get(Item, with db.get(Product,
    sed -i 's/db\.get(Item,/db.get(Product,/g' "$file"

    echo "  ✓ Updated Item class usage in $file"
done

echo ""
echo "Fix complete!"
echo ""
echo "Summary:"
echo "- Replaced 'Item' imports with 'Product' imports"
echo "- Replaced db.query(Item) with db.query(Product)"
echo "- Replaced db.get(Item with db.get(Product"
echo "- Removed ItemNodeConfig and ItemNodeSupplier imports"
echo ""
echo "Next: Restart backend to test"
