#!/bin/bash
# Script to update all model files from Item to Product references

echo "Updating model files to use Product table instead of Item table..."

# List of files to update
FILES=(
    "backend/app/models/purchase_order.py"
    "backend/app/models/transfer_order.py"
    "backend/app/models/production_order.py"
    "backend/app/models/mrp.py"
    "backend/app/models/inventory_projection.py"
    "backend/app/models/sc_planning.py"
    "backend/app/models/supplier.py"
)

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "Updating $file..."

        # Update ForeignKey references from items.id to product.id with Integer to String(100)
        sed -i 's/Column(Integer, ForeignKey("items\.id")/Column(String(100), ForeignKey("product.id")/g' "$file"

        # Update relationship references from "Item" to "Product"
        sed -i 's/relationship("Item"/relationship("Product"/g' "$file"

        echo "  ✓ Updated $file"
    else
        echo "  ✗ File not found: $file"
    fi
done

echo ""
echo "Update complete! Summary:"
echo "- Changed ForeignKey(\"items.id\") → ForeignKey(\"product.id\")"
echo "- Changed Column(Integer, ...) → Column(String(100), ...)"
echo "- Changed relationship(\"Item\") → relationship(\"Product\")"
echo ""
echo "Next: Review changes and restart backend to test"
