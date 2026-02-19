# Quick Start: Phase 1 Migration (Non-Breaking)

**Ready to deploy NOW** - No code changes required!

---

## What This Does

Adds AWS Supply Chain standard fields to your database **without breaking anything**. All new fields are optional or have defaults. Your existing code will continue to work exactly as before.

---

## Pre-Flight Checklist

- [ ] Database is healthy
- [ ] No games in progress (optional, but recommended)
- [ ] Backup created (see below)

---

## Step-by-Step Instructions

### 1. Backup Your Database (CRITICAL!)

```bash
# Create backup
docker compose exec db mysqldump -u root -p19890617 beer_game > backup_$(date +%Y%m%d).sql

# Verify backup exists and has size
ls -lh backup_*.sql

# You should see something like: backup_20260107.sql (several MB)
```

### 2. Check Current Migration State

```bash
# See current database version
docker compose exec backend alembic current

# You should see: 20260107_item_node_supplier (head)
```

### 3. Restart Backend (Pick Up New Migration Files)

```bash
docker compose restart backend

# Wait a few seconds for restart
sleep 5
```

### 4. Verify New Migrations Are Detected

```bash
# Check all available migrations
docker compose exec backend alembic history | head -10

# You should now see:
# - 20260107_aws_optional
# - 20260107_aws_entities
```

### 5. Run Phase 1 Migrations

```bash
# Apply optional fields migration
docker compose exec backend alembic upgrade 20260107_aws_optional

# Apply new entity tables migration
docker compose exec backend alembic upgrade 20260107_aws_entities
```

### 6. Verify Success

```bash
# Check current version
docker compose exec backend alembic current

# You should see: 20260107_aws_entities (head)

# Verify new tables exist
docker compose exec db mysql -u root -p19890617 beer_game -e "SHOW TABLES LIKE '%geography%'; SHOW TABLES LIKE '%product_hierarchy%'; SHOW TABLES LIKE '%trading_partner%';"
```

### 7. Test Your Application

```bash
# Access the application
open http://localhost:8088

# Test:
# 1. Login
# 2. View supply chain configs
# 3. Create a new config (or edit existing)
# 4. Start a game
# 5. Play a round

# Everything should work exactly as before!
```

---

## What Changed?

### New Fields Added to Existing Tables

**nodes table**:
- `geo_id`, `latitude`, `longitude`
- `is_active`, `open_date`, `end_date`
- `site_type` (copy of `type`), `description` (copy of `name`)

**items table**:
- `product_group_id`, `is_deleted`
- `product_type`, `parent_product_id`
- `base_uom`, `unit_cost`, `unit_price`

**lanes table**:
- `from_geo_id`, `to_geo_id`
- `carrier_tpartner_id`, `service_type`, `trans_mode`
- `distance`, `distance_uom`
- `emissions_per_unit`, `emissions_per_weight`
- `cost_per_unit`, `cost_currency`
- `eff_start_date`, `eff_end_date`
- `transit_time` (from `supply_lead_time.value`), `time_uom`

**item_node_suppliers table**:
- `sourcing_rule_type`, `min_qty`, `max_qty`, `qty_multiple`
- `eff_start_date`, `eff_end_date`

### New Tables Created

1. **geography** - With sample data (World → North America → United States → Regions)
2. **product_hierarchy** - With sample categories (Beverages → Beer, Food, etc.)
3. **trading_partner** - Empty, ready for vendor data

---

## Using the New Fields

You can now start populating these fields in your code:

### Example: Setting Geographic Location

```python
# In your supply chain config service
node.geo_id = 4  # USA-EAST
node.latitude = 40.7128
node.longitude = -74.0060
node.is_active = True
```

### Example: Setting Product Category

```python
# When creating items
item.product_group_id = 4  # Beer category
item.base_uom = "case"
item.unit_cost = 10.50
item.unit_price = 15.00
```

### Example: Setting Sourcing Rules

```python
# When configuring sourcing
supplier.sourcing_rule_type = "transfer"
supplier.min_qty = 10
supplier.max_qty = 1000
supplier.qty_multiple = 10  # Must order in multiples of 10
```

---

## Rollback Instructions

If something goes wrong:

```bash
# 1. Stop the application
docker compose stop backend

# 2. Downgrade migrations (in reverse order)
docker compose exec backend alembic downgrade 20260107_aws_optional
docker compose exec backend alembic downgrade 20260107_item_node_supplier

# 3. Or restore from backup
docker compose exec db mysql -u root -p19890617 beer_game < backup_20260107.sql

# 4. Restart
docker compose restart backend
```

---

## Verification Queries

Check that new fields exist:

```bash
# Check nodes table
docker compose exec db mysql -u root -p19890617 beer_game -e "DESCRIBE nodes;" | grep -E "geo_id|latitude|is_active|site_type|description"

# Check items table
docker compose exec db mysql -u root -p19890617 beer_game -e "DESCRIBE items;" | grep -E "product_group_id|is_deleted|unit_cost|unit_price"

# Check new tables
docker compose exec db mysql -u root -p19890617 beer_game -e "SELECT * FROM geography;"
docker compose exec db mysql -u root -p19890617 beer_game -e "SELECT * FROM product_hierarchy;"
```

---

## Next Steps

### Option 1: Start Using New Fields (Recommended)

Update your code to start populating the new AWS-standard fields:

1. Set `geo_id` when creating nodes
2. Set `product_group_id` when creating items
3. Set `is_active`, `is_deleted` flags appropriately
4. Populate unit costs and prices

Benefits:
- Richer data for analytics
- Preparation for Phase 2 (field renames)
- AWS-compliant data structure

### Option 2: Monitor & Wait

Keep the new fields for now, but don't actively use them. They won't hurt anything and are ready when needed.

### Option 3: Plan Phase 2

If you want full AWS compliance with field renames (`item_id` → `product_id`, etc.), start planning the Phase 2 migration:

1. Review [FIELD_NAME_REFERENCE.md](FIELD_NAME_REFERENCE.md)
2. Review [CODE_SWEEP_REPORT.md](CODE_SWEEP_REPORT.md)
3. Schedule 6-8 weeks for code updates
4. Create detailed project plan

---

## Troubleshooting

### Migration fails with "table already exists"

Some fields might have been added in a previous session. The migrations handle this gracefully - they check if fields exist before adding.

### Can't connect to database

```bash
# Restart database
docker compose restart db

# Wait for healthy status
docker compose ps db
```

### Alembic says "already at head"

The migrations are already applied. Check:

```bash
docker compose exec backend alembic current
```

---

## FAQ

**Q: Will this break my existing games?**
A: No. All changes are additive. Existing data and code work exactly as before.

**Q: Do I need to update my code?**
A: No, not for Phase 1. Code changes are only required for Phase 2 (field renames).

**Q: Can I roll back?**
A: Yes, easily. Run the downgrade commands or restore from backup.

**Q: How long does the migration take?**
A: 1-2 minutes typically. Adding columns and creating empty tables is fast.

**Q: Will there be downtime?**
A: Minimal. You can run migrations while the app is running, but it's safer to restart the backend first.

**Q: What if I don't want all these new fields?**
A: They're optional and won't affect your existing functionality. You can ignore them or roll back.

---

## Success Criteria

✅ Migration runs without errors
✅ Application starts successfully
✅ Can view existing supply chain configs
✅ Can create/edit configs
✅ Can start and play games
✅ No error logs in backend

---

## Support

If you encounter issues:

1. Check the error message in backend logs:
   ```bash
   docker compose logs backend --tail=50
   ```

2. Verify database connectivity:
   ```bash
   docker compose exec backend python -c "from app.db.session import engine; print(engine)"
   ```

3. Check alembic version table:
   ```bash
   docker compose exec db mysql -u root -p19890617 beer_game -e "SELECT * FROM alembic_version;"
   ```

---

**Ready?** Follow the steps above and you'll have AWS-standard fields in ~5 minutes!

**Questions?** Review [AWS_MIGRATION_EXECUTIVE_SUMMARY.md](AWS_MIGRATION_EXECUTIVE_SUMMARY.md) for the big picture.
