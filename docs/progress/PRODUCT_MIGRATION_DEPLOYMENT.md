# Product Migration: Production Deployment Guide

**Migration Status**: Development Complete ✅
**Created**: January 22, 2026
**Purpose**: Step-by-step guide for deploying Item → Product migration to production

---

## 🎯 Overview

This guide provides a comprehensive procedure for deploying the Item → Product migration to production environments. The migration achieves full AWS Supply Chain compliance for the Product entity with zero-downtime architecture.

**Migration Scope**:
- ✅ Database: 26 items → 26 products with String IDs
- ✅ Models: 38+ foreign keys migrated to String(100)
- ✅ Services: All 30+ service files Product-compatible
- ✅ API: 5 Product CRUD endpoints operational
- ✅ Compatibility layer for gradual transition

---

## ⚠️ Pre-Deployment Checklist

### 1. Environment Verification

```bash
# Verify staging environment matches production
- [ ] Database version matches (MariaDB 10.11+)
- [ ] Python version matches (3.10+)
- [ ] All dependencies up-to-date (requirements.txt)
- [ ] Environment variables configured
- [ ] Backup system operational
```

### 2. Team Readiness

- [ ] On-call engineer assigned
- [ ] Rollback procedure documented and tested
- [ ] Stakeholders notified of maintenance window
- [ ] Communication channels established (Slack, email, etc.)
- [ ] Post-deployment monitoring plan in place

### 3. Backup Strategy

```bash
# Create full database backup BEFORE migration
docker exec the_beer_game_db mariadb-dump \
  -u beer_user -pbeer_password \
  beer_game > backup_pre_product_migration_$(date +%Y%m%d_%H%M%S).sql

# Verify backup size and integrity
ls -lh backup_pre_product_migration_*.sql
gzip backup_pre_product_migration_*.sql

# Store backup in safe location
aws s3 cp backup_pre_product_migration_*.sql.gz \
  s3://your-backup-bucket/migrations/product/
```

### 4. Staging Validation

- [ ] Migration script tested on staging copy of production data
- [ ] All 8 phases completed successfully in staging
- [ ] Beer Game playable in staging
- [ ] Performance metrics acceptable
- [ ] No critical errors in logs
- [ ] Frontend UI tested (even with partial completion)

---

## 📋 Deployment Procedure

### Phase 1: Pre-Deployment (30 minutes)

#### 1.1 Schedule Maintenance Window

**Recommended**: Off-peak hours, 2-hour window

```
Maintenance Window: [DATE] [START_TIME] - [END_TIME]
Expected Downtime: 0 seconds (rolling deployment)
Fallback Plan: Immediate rollback if critical issues
```

#### 1.2 Notify Stakeholders

**Email Template**:
```
Subject: The Beer Game - Product Migration Deployment

We will be deploying a major backend enhancement to achieve AWS Supply Chain
compliance for the Product entity.

When: [DATE] [START_TIME] - [END_TIME]
Expected Impact: None (zero-downtime deployment)
What's Changing: Internal data model (Item → Product)
User Impact: No functional changes, system remains fully operational

The deployment will be closely monitored with immediate rollback capability.

Questions? Contact: [YOUR_EMAIL]
```

#### 1.3 Enable Enhanced Monitoring

```bash
# Increase log verbosity temporarily
export LOG_LEVEL=DEBUG

# Enable query logging (MariaDB)
docker exec the_beer_game_db mariadb -u root -p \
  -e "SET GLOBAL general_log = 'ON';"
  -e "SET GLOBAL slow_query_log = 'ON';"
  -e "SET GLOBAL long_query_time = 1;"

# Start monitoring dashboard
docker compose logs -f backend | tee deployment_$(date +%Y%m%d_%H%M%S).log
```

---

### Phase 2: Code Deployment (15 minutes)

#### 2.1 Deploy Backend Code

**Option A: Docker Deployment**
```bash
# Pull latest code
git pull origin main

# Rebuild backend image
docker compose build backend

# Deploy with rolling update (zero downtime)
docker compose up -d --no-deps --build backend

# Monitor startup
docker compose logs -f backend
```

**Option B: Manual Deployment**
```bash
# Pull code
cd /opt/the_beer_game/backend
git pull origin main

# Install dependencies
pip install -r requirements.txt

# Reload application (zero downtime with Gunicorn)
kill -HUP $(cat /var/run/gunicorn.pid)

# Verify reload
curl http://localhost:8000/api/health
```

#### 2.2 Verify Backend Health

```bash
# Health check
curl -s http://localhost:8088/api/health | jq .
# Expected: {"status":"ok","time":"..."}

# Check product endpoints
curl -s http://localhost:8088/api/v1/supply-chain-configs/1/products \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '. | length'
# Expected: Product count (0 before migration, 26+ after)
```

---

### Phase 3: Database Migration (45 minutes)

#### 3.1 Run Migration Script

**⚠️ CRITICAL**: This is the most sensitive phase

```bash
# Navigate to backend
cd /opt/the_beer_game/backend

# Run migration script (with dry-run first)
python scripts/migrate_items_to_products.py --dry-run

# Review dry-run output carefully
# Verify:
# - Product count matches expected
# - BOM count matches expected
# - No orphaned records
# - String ID format looks correct

# Execute actual migration
python scripts/migrate_items_to_products.py --execute

# Monitor progress
tail -f logs/migration_$(date +%Y%m%d).log
```

**Expected Output**:
```
[INFO] Starting Item → Product migration
[INFO] Found 26 items to migrate
[INFO] Generating String IDs: Case → CASE, Six-Pack → SIXPACK, ...
[INFO] Creating DEFAULT company
[INFO] Migrating products... 26/26 complete
[INFO] Extracting BOMs from JSON... 10 BOMs created
[INFO] Marking key materials... 5 flagged
[INFO] Updating foreign keys... 38+ FKs updated
[INFO] ✅ Migration complete! No errors.
[INFO] Summary:
  - Products created: 26
  - BOMs extracted: 10
  - Key materials: 5
  - Duration: 45 seconds
```

#### 3.2 Verify Migration Success

```bash
# Verify product count
docker exec the_beer_game_db mariadb -u beer_user -pbeer_password beer_game \
  -e "SELECT COUNT(*) as product_count FROM product;"
# Expected: 26

# Verify String IDs
docker exec the_beer_game_db mariadb -u beer_user -pbeer_password beer_game \
  -e "SELECT id, description FROM product LIMIT 5;"
# Expected: String IDs like CASE, SIXPACK, BOTTLE

# Verify BOMs
docker exec the_beer_game_db mariadb -u beer_user -pbeer_password beer_game \
  -e "SELECT COUNT(*) as bom_count FROM product_bom;"
# Expected: 10

# Verify key materials
docker exec the_beer_game_db mariadb -u beer_user -pbeer_password beer_game \
  -e "SELECT COUNT(*) as key_material_count FROM product_bom WHERE is_key_material='true';"
# Expected: 5

# Check for orphaned foreign keys
docker exec the_beer_game_db mariadb -u beer_user -pbeer_password beer_game \
  -e "SELECT COUNT(*) FROM market_demands md LEFT JOIN product p ON md.product_id = p.id WHERE p.id IS NULL;"
# Expected: 0 (no orphans)
```

#### 3.3 Restart Backend (if needed)

```bash
# Restart to pick up model changes
docker compose restart backend

# Wait for startup
sleep 10

# Verify health
curl -s http://localhost:8088/api/health | jq .
# Expected: {"status":"ok"}
```

---

### Phase 4: Smoke Testing (20 minutes)

#### 4.1 API Endpoint Testing

```bash
# Test Product CRUD
export TOKEN="your_admin_token"
export CONFIG_ID=1

# List products
curl -s http://localhost:8088/api/v1/supply-chain-configs/$CONFIG_ID/products \
  -H "Authorization: Bearer $TOKEN" | jq '. | length'
# Expected: 26+

# Get specific product
curl -s http://localhost:8088/api/v1/supply-chain-configs/$CONFIG_ID/products/CASE \
  -H "Authorization: Bearer $TOKEN" | jq .
# Expected: Product object with id="CASE"

# Create test product
curl -X POST http://localhost:8088/api/v1/supply-chain-configs/$CONFIG_ID/products \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "SMOKETEST",
    "description": "Smoke test product",
    "company_id": "DEFAULT",
    "product_type": "finished_good",
    "base_uom": "EA"
  }' | jq .
# Expected: 201 Created

# Delete test product
curl -X DELETE http://localhost:8088/api/v1/supply-chain-configs/$CONFIG_ID/products/SMOKETEST \
  -H "Authorization: Bearer $TOKEN"
# Expected: 204 No Content
```

#### 4.2 Beer Game Testing

```bash
# Create test game
GAME_ID=$(curl -s -X POST http://localhost:8088/api/v1/mixed-games \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "config_id": 1,
    "name": "Production Smoke Test",
    "max_rounds": 3,
    "players": [
      {"role": "retailer", "type": "ai", "strategy": "naive"},
      {"role": "wholesaler", "type": "ai", "strategy": "naive"},
      {"role": "distributor", "type": "ai", "strategy": "naive"},
      {"role": "factory", "type": "ai", "strategy": "naive"}
    ]
  }' | jq -r '.id')

echo "Game ID: $GAME_ID"

# Start game
curl -X POST http://localhost:8088/api/v1/mixed-games/$GAME_ID/start \
  -H "Authorization: Bearer $TOKEN"

# Play 3 rounds
for i in {1..3}; do
  echo "Playing round $i..."
  curl -X POST http://localhost:8088/api/v1/mixed-games/$GAME_ID/play-round \
    -H "Authorization: Bearer $TOKEN"
  sleep 2
done

# Get game state
curl -s http://localhost:8088/api/v1/mixed-games/$GAME_ID/state \
  -H "Authorization: Bearer $TOKEN" | jq '.current_round'
# Expected: 3

# Verify no errors in logs
docker compose logs backend --tail=50 | grep -i error
# Expected: No critical errors
```

#### 4.3 Performance Validation

```bash
# Check response times
for i in {1..10}; do
  time curl -s http://localhost:8088/api/v1/supply-chain-configs/1/products \
    -H "Authorization: Bearer $TOKEN" > /dev/null
done
# Expected: All requests < 500ms

# Check database query performance
docker exec the_beer_game_db mariadb -u beer_user -pbeer_password beer_game \
  -e "EXPLAIN SELECT * FROM product WHERE id = 'CASE';"
# Expected: Uses PRIMARY KEY, type=const
```

---

### Phase 5: Monitor & Validate (30 minutes)

#### 5.1 Monitor Key Metrics

**Application Metrics**:
- [ ] Response times normal (< 500ms for product APIs)
- [ ] Error rate acceptable (< 0.1%)
- [ ] Active connections stable
- [ ] Memory usage normal
- [ ] CPU usage normal

**Database Metrics**:
- [ ] Query times normal (< 100ms for product lookups)
- [ ] Connection pool healthy
- [ ] No lock contention
- [ ] Replication lag acceptable (if applicable)

**System Metrics**:
- [ ] Disk I/O normal
- [ ] Network traffic normal
- [ ] No disk space issues

#### 5.2 Check Logs for Errors

```bash
# Backend errors (last hour)
docker compose logs backend --since 1h | grep -i error | grep -i product

# Database errors
docker compose logs db --since 1h | grep -i error

# Application errors
grep -i "500\|502\|503" /var/log/nginx/access.log | tail -50
```

#### 5.3 Validate User Functionality

- [ ] Login works
- [ ] Supply chain configs load
- [ ] Game creation works
- [ ] Games can be played
- [ ] Reports generate correctly
- [ ] No UI errors (check browser console)

---

### Phase 6: Post-Deployment (15 minutes)

#### 6.1 Update Documentation

```bash
# Tag release
git tag -a v2.0-product-migration -m "Item → Product migration complete"
git push origin v2.0-product-migration

# Update CHANGELOG
echo "## v2.0 - Product Migration ($(date +%Y-%m-%d))" >> CHANGELOG.md
echo "- Migrated from Item to AWS SC Product model" >> CHANGELOG.md
echo "- 26 products with String IDs" >> CHANGELOG.md
echo "- 10 BOMs extracted to ProductBom table" >> CHANGELOG.md
echo "- 5 key materials flagged" >> CHANGELOG.md
```

#### 6.2 Notify Success

**Email Template**:
```
Subject: ✅ The Beer Game - Product Migration Deployed Successfully

The Product migration has been successfully deployed to production.

Status: Complete ✅
Downtime: 0 seconds
Issues: None
Performance: Normal

Changes:
- Backend now uses AWS SC compliant Product model
- All 26 products migrated successfully
- System fully operational

Monitoring will continue for the next 24 hours. No user action required.

Questions? Contact: [YOUR_EMAIL]
```

#### 6.3 Disable Enhanced Monitoring

```bash
# Reduce log verbosity after 24 hours
export LOG_LEVEL=INFO

# Disable query logging
docker exec the_beer_game_db mariadb -u root -p \
  -e "SET GLOBAL general_log = 'OFF';"
```

---

## 🚨 Rollback Procedure

### If Critical Issues Detected

**Decision Criteria for Rollback**:
- Error rate > 5%
- Critical functionality broken
- Data corruption detected
- Performance degradation > 50%
- User-facing errors

### Rollback Steps (30 minutes)

```bash
# 1. Stop traffic (if needed)
# Redirect to maintenance page

# 2. Stop backend
docker compose stop backend

# 3. Restore database backup
gunzip backup_pre_product_migration_*.sql.gz
docker exec -i the_beer_game_db mariadb -u beer_user -pbeer_password beer_game \
  < backup_pre_product_migration_*.sql

# 4. Revert code
git revert <product-migration-commit-range>
docker compose build backend

# 5. Restart backend
docker compose up -d backend

# 6. Verify rollback
curl -s http://localhost:8088/api/health | jq .

# 7. Smoke test
# (Run Phase 4 smoke tests again)

# 8. Re-enable traffic
# Remove maintenance page

# 9. Monitor closely
docker compose logs -f backend

# 10. Notify stakeholders
# Send rollback notification email
```

### Post-Rollback Analysis

- [ ] Document what went wrong
- [ ] Analyze root cause
- [ ] Update migration procedure
- [ ] Re-test in staging
- [ ] Schedule new deployment

---

## 📊 Success Criteria

### Deployment Successful If:

✅ All smoke tests pass
✅ No critical errors in logs
✅ Response times normal (< 500ms)
✅ Error rate acceptable (< 0.1%)
✅ All 26 products present
✅ Beer Game playable
✅ Product CRUD operations work
✅ No data loss or corruption
✅ Foreign key integrity maintained
✅ User functionality unchanged

---

## 📈 Post-Deployment Monitoring

### Week 1: Enhanced Monitoring

**Daily Checks**:
- [ ] Error logs review
- [ ] Performance metrics
- [ ] User feedback
- [ ] Database integrity
- [ ] Backup verification

**Weekly Report**:
- [ ] Total requests processed
- [ ] Average response time
- [ ] Error count and types
- [ ] User satisfaction
- [ ] Performance trends

### Month 1: Standard Monitoring

**Weekly Checks**:
- [ ] Performance metrics normal
- [ ] No degradation trends
- [ ] Error rates stable
- [ ] Database size growth normal

**Monthly Review**:
- [ ] Migration success evaluation
- [ ] Performance vs. pre-migration
- [ ] Lessons learned documentation
- [ ] Future optimization opportunities

---

## 🎯 Next Steps After Deployment

### Short Term (Week 1-2)
1. Monitor system closely for any issues
2. Collect user feedback
3. Document any unexpected behaviors
4. Optimize queries if performance issues

### Medium Term (Month 1-3)
1. Complete frontend UI updates (ItemForm.jsx)
2. Update seed scripts for fresh installations
3. Create Alembic migration for new environments
4. Remove compatibility layer (after confidence)

### Long Term (Month 3-6)
1. Performance optimization with String PKs
2. Add advanced Product features
3. Integrate with external AWS SC systems
4. Train team on AWS SC data model

---

## 📞 Support & Escalation

### During Deployment

**Primary Contact**: [NAME] - [PHONE] - [EMAIL]
**Backup Contact**: [NAME] - [PHONE] - [EMAIL]
**Escalation**: [CTO/VP Eng] - [PHONE] - [EMAIL]

### Communication Channels

- **Slack**: #deployment-alerts
- **Email**: devops@company.com
- **On-Call**: PagerDuty

---

## 📚 Reference Documentation

- [MIGRATION_STATUS.md](MIGRATION_STATUS.md) - Complete migration status
- [PRODUCT_MIGRATION_GUIDE.md](PRODUCT_MIGRATION_GUIDE.md) - Developer guide
- [PRODUCT_MIGRATION_TESTING.md](PRODUCT_MIGRATION_TESTING.md) - Testing checklist
- [MIGRATION_SUMMARY.md](MIGRATION_SUMMARY.md) - Migration summary

---

**Document Version**: 1.0
**Last Updated**: January 22, 2026
**Deployment Status**: Development Complete, Production Pending
**Estimated Deployment Time**: 2 hours (with 0 seconds downtime)

*For questions or concerns, contact the DevOps team.*
