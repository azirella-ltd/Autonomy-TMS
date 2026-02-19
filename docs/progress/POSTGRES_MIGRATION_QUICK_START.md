# PostgreSQL Migration - Quick Start Guide

**Goal**: Migrate The Beer Game from MariaDB 10.11 to PostgreSQL 16
**Time**: 3-4 days (16-24 hours total)
**Status**: Ready to Begin

---

## 📋 Pre-Flight Checklist

Before starting, ensure you have:

- [x] Read [MARIADB_TO_POSTGRESQL_MIGRATION_PLAN.md](MARIADB_TO_POSTGRESQL_MIGRATION_PLAN.md)
- [ ] Created git branch: `git checkout -b postgres-migration`
- [ ] Backed up MariaDB: `make db-backup` (or manual backup)
- [ ] Development environment available for testing
- [ ] ~20 hours available over 3-4 days

---

## 🚀 Quick Start (30 Minutes)

### Step 1: Backup Current Database (5 min)

```bash
# Create backup directory
mkdir -p backups/mariadb_$(date +%Y%m%d)

# Backup MariaDB data
docker compose exec db mysqldump \
  -u root -p19890617 \
  --databases beer_game \
  --single-transaction \
  --quick \
  --lock-tables=false \
  > backups/mariadb_$(date +%Y%m%d)/beer_game_full_backup.sql

# Verify backup
ls -lh backups/mariadb_$(date +%Y%m%d)/
```

### Step 2: Create Migration Branch (1 min)

```bash
git add -A
git commit -m "Pre-migration snapshot: MariaDB baseline"
git tag mariadb-baseline-$(date +%Y%m%d)
git checkout -b postgres-migration
```

### Step 3: Update Dependencies (5 min)

**File**: `backend/requirements.txt`

```bash
# Remove MySQL dependencies (lines 12-15)
# - pymysql==1.1.0
# - aiomysql==0.2.0
# - asyncmy==0.2.7
# - mysql-connector-python==8.0.33

# Add PostgreSQL dependencies
cat >> backend/requirements.txt << 'EOF'

# PostgreSQL Database Drivers
psycopg2-binary==2.9.9
asyncpg==0.29.0
EOF
```

### Step 4: Update Dockerfiles (10 min)

**Files**: `backend/Dockerfile.cpu`, `backend/Dockerfile.gpu`, `backend/Dockerfile.prod`

Replace in all 3 files:
```diff
- default-mysql-client
- libmariadb-dev
- libmariadb-dev-compat
+ postgresql-client
+ libpq-dev
```

**Example** (apply to all 3 Dockerfiles):
```bash
# Dockerfile.cpu
sed -i 's/default-mysql-client/postgresql-client/' backend/Dockerfile.cpu
sed -i 's/libmariadb-dev.*$/libpq-dev \\/' backend/Dockerfile.cpu

# Dockerfile.gpu
sed -i 's/default-mysql-client/postgresql-client/' backend/Dockerfile.gpu
sed -i 's/libmariadb-dev.*$/libpq-dev \\/' backend/Dockerfile.gpu

# Dockerfile.prod
sed -i 's/default-mysql-client/postgresql-client/' backend/Dockerfile.prod
sed -i 's/libmariadb-dev.*$/libpq-dev \\/' backend/Dockerfile.prod
```

### Step 5: Update Database Connection Logic (5 min)

**File**: `backend/app/core/db_urls.py`

Add PostgreSQL support function (see full implementation in migration plan):

```python
def _postgres_url(sync: bool = True) -> str:
    """Construct PostgreSQL connection URL from environment variables."""
    host = os.getenv("POSTGRESQL_HOST") or os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRESQL_PORT") or os.getenv("POSTGRES_PORT", "5432"))
    database = os.getenv("POSTGRESQL_DATABASE") or os.getenv("POSTGRES_DB", "beer_game")
    user = os.getenv("POSTGRESQL_USER") or os.getenv("POSTGRES_USER", "beer_user")
    password = os.getenv("POSTGRESQL_PASSWORD") or os.getenv("POSTGRES_PASSWORD", "beer_password")

    driver = "psycopg2" if sync else "asyncpg"
    return f"postgresql+{driver}://{user}:{password}@{host}:{port}/{database}"
```

Update `get_database_url()` to support both databases (see Section 4.3 in migration plan).

### Step 6: Create PostgreSQL Configuration (5 min)

**File**: `postgresql.conf` (NEW)

```bash
cat > postgresql.conf << 'EOF'
# PostgreSQL Configuration for The Beer Game
listen_addresses = '*'
port = 5432
max_connections = 200

# Memory Settings
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 4MB
maintenance_work_mem = 64MB

# Logging
logging_collector = on
log_directory = 'pg_log'
log_statement = 'none'
log_line_prefix = '%t [%p]: user=%u,db=%d '

# Connection Timeouts
tcp_keepalives_idle = 600

# Autovacuum
autovacuum = on
autovacuum_max_workers = 3

# Locale
timezone = 'UTC'
lc_messages = 'en_US.UTF-8'
EOF
```

---

## 📝 Day-by-Day Plan

### **Day 1: Preparation** (4-6 hours)

**Morning** (2-3 hours):
1. ✅ Backup MariaDB ← Done above
2. ✅ Create git branch ← Done above
3. ✅ Update requirements.txt ← Done above
4. ✅ Update Dockerfiles ← Done above
5. ✅ Update db_urls.py ← Done above
6. ✅ Create postgresql.conf ← Done above

**Afternoon** (2-3 hours):
7. Update Docker Compose files (see Section 4.4 in plan)
8. Create `init_db_postgres.sql` (see Section 4.5 in plan)
9. Update `.env` file (see Section 4.8 in plan)
10. Update `backend/app/db/init_db.py` (see Section 4.6 in plan)
11. Update `backend/alembic.ini` and `alembic/env.py` (see Sections 4.9-4.10)
12. Commit all changes

**Deliverable**: All code ready for PostgreSQL (not yet running)

---

### **Day 2: Migration** (4-6 hours)

**Morning** (2-3 hours):
1. Build new Docker images: `docker compose build`
2. Start PostgreSQL: `docker compose up -d db`
3. Wait for ready: `docker compose exec db pg_isready -U beer_user -d beer_game`
4. Run init_db.py: `docker compose exec backend python -m app.db.init_db`
5. Verify tables: `docker compose exec db psql -U beer_user -d beer_game -c "\dt"`
   - Should show 97 tables

**Afternoon** (2-3 hours):
6. Export MariaDB data (already done in Day 1 backup)
7. Convert SQL dump to PostgreSQL format (use script from Section 5.2)
8. Import data into PostgreSQL (see Section 5.3)
9. Reset sequences (see Section 10.3 workaround)
10. Validate data (see Section 5.4)

**Deliverable**: PostgreSQL database with all 97 tables and data

---

### **Day 3: Testing** (6-8 hours)

**Morning** (3-4 hours):
1. Start all services: `docker compose up -d`
2. Health check: `curl http://localhost:8000/health`
3. Test authentication
4. Test game creation
5. Test gameplay (play 10 rounds)
6. Test all agent strategies

**Afternoon** (3-4 hours):
7. Test GNN training
8. Test API endpoints (sample 20-30 critical ones)
9. Run validation script (see Section 8.2)
10. Performance benchmarking
11. Document issues
12. Fix critical issues

**Deliverable**: Fully tested PostgreSQL system

---

### **Day 4: Production** (2-4 hours)

1. Schedule maintenance window
2. Final MariaDB backup
3. Deploy PostgreSQL configuration
4. Migrate production data
5. Start services
6. Smoke tests
7. Monitor for 24 hours

**Deliverable**: Production running on PostgreSQL

---

## 🔥 Fast Track (1 Day - Development Only)

If you're migrating a development environment and can afford some risk:

### Morning (4 hours)

```bash
# 1. Backup
mkdir -p backups && docker compose exec db mysqldump -u root -p19890617 beer_game > backups/mariadb_backup.sql

# 2. Update code (all steps from "Quick Start" above)
# ... (30 minutes of file edits)

# 3. Update Docker Compose
# Replace db service in docker-compose.yml (see Section 4.4)

# 4. Update .env
cat >> .env << 'EOF'
DATABASE_TYPE=postgresql
POSTGRESQL_HOST=db
POSTGRESQL_PORT=5432
POSTGRESQL_DATABASE=beer_game
POSTGRESQL_USER=beer_user
POSTGRESQL_PASSWORD=beer_password
EOF

# 5. Rebuild and start
docker compose down
docker compose build backend
docker compose up -d
```

### Afternoon (4 hours)

```bash
# 6. Create schema
docker compose exec backend python -m app.db.init_db

# 7. Import data (use pgloader or conversion script)
# ... (see Section 5 in plan)

# 8. Test everything
./scripts/validate_postgres_migration.sh

# 9. Fix issues as they arise
```

---

## 🛠️ Essential Commands

### PostgreSQL Shell

```bash
# Connect to database
docker compose exec db psql -U beer_user -d beer_game

# Inside psql:
\dt                    # List tables
\d+ users              # Describe table
\di                    # List indexes
\df                    # List functions
\l                     # List databases
\q                     # Quit
```

### Data Validation

```bash
# Row counts
docker compose exec db psql -U beer_user -d beer_game -c "
SELECT schemaname, tablename, n_live_tup AS row_count
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC
LIMIT 20;
"

# Table sizes
docker compose exec db psql -U beer_user -d beer_game -c "
SELECT tablename,
       pg_size_pretty(pg_total_relation_size('public.'||tablename)) AS size
FROM pg_tables
WHERE schemaname='public'
ORDER BY pg_total_relation_size('public.'||tablename) DESC
LIMIT 20;
"

# Active connections
docker compose exec db psql -U beer_user -d beer_game -c "
SELECT COUNT(*), state FROM pg_stat_activity
WHERE datname='beer_game'
GROUP BY state;
"
```

### Testing

```bash
# Backend health
curl http://localhost:8000/health

# Login
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"systemadmin@autonomy.ai","password":"Autonomy@2025"}' \
  | jq -r '.access_token')

# Test authenticated endpoint
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/users/me

# Create test game
curl -X POST http://localhost:8000/api/v1/agent-games/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "PostgreSQL Test Game",
    "config_name": "Default TBG",
    "max_rounds": 24
  }'
```

---

## 🆘 Troubleshooting

### Issue: Backend won't start

```bash
# Check logs
docker compose logs backend --tail 100

# Common issues:
# 1. Missing dependencies → rebuild: docker compose build backend
# 2. Connection error → check .env DATABASE_URL
# 3. Import error → check db_urls.py implementation
```

### Issue: Tables not created

```bash
# Manually create tables
docker compose exec backend python -c "
from app.db.session import engine
from app.models.base import Base
Base.metadata.create_all(bind=engine)
print('Tables created')
"

# Verify
docker compose exec db psql -U beer_user -d beer_game -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';"
```

### Issue: Data import failed

```bash
# Check PostgreSQL logs
docker compose logs db --tail 200

# Common issues:
# 1. Sequence errors → Reset sequences (see Section 10.3)
# 2. ENUM errors → Create ENUM types first (see Section 10.2)
# 3. Foreign key errors → Import in correct order (parents before children)
```

### Issue: Slow performance

```bash
# Check cache hit ratio (should be > 95%)
docker compose exec db psql -U beer_user -d beer_game -c "
SELECT SUM(heap_blks_hit) / (SUM(heap_blks_hit) + SUM(heap_blks_read)) * 100 AS cache_hit_ratio
FROM pg_statio_user_tables;
"

# Analyze tables
docker compose exec db psql -U beer_user -d beer_game -c "ANALYZE;"

# Check missing indexes
docker compose exec db psql -U beer_user -d beer_game -c "
SELECT schemaname, tablename, seq_scan, idx_scan
FROM pg_stat_user_tables
WHERE seq_scan > idx_scan AND seq_scan > 100
ORDER BY seq_scan DESC
LIMIT 10;
"
```

---

## 📚 Key Files Reference

| File | Purpose | Status |
|------|---------|--------|
| [MARIADB_TO_POSTGRESQL_MIGRATION_PLAN.md](MARIADB_TO_POSTGRESQL_MIGRATION_PLAN.md) | **Complete migration guide** | ✅ Created |
| `backend/requirements.txt` | Python dependencies | ⏳ Update |
| `backend/Dockerfile.*` | Docker build configs | ⏳ Update |
| `backend/app/core/db_urls.py` | Database URL resolver | ⏳ Update |
| `backend/app/db/init_db.py` | Database initialization | ⏳ Update |
| `docker-compose.yml` | Docker services | ⏳ Update |
| `postgresql.conf` | PostgreSQL config | ⏳ Create |
| `init_db_postgres.sql` | DB initialization SQL | ⏳ Create |
| `.env` | Environment variables | ⏳ Update |
| `backend/alembic.ini` | Alembic config | ⏳ Update |
| `backend/alembic/env.py` | Alembic environment | ⏳ Update |

---

## ✅ Validation Checklist

After migration, verify:

- [ ] **Backend starts** without errors
- [ ] **97 tables** exist in PostgreSQL
- [ ] **Row counts** match MariaDB for all tables
- [ ] **Login works** (systemadmin@autonomy.ai)
- [ ] **Game creation** works
- [ ] **Gameplay** works (play 5 rounds successfully)
- [ ] **All agent types** work (naive, conservative, ml_forecast, llm, etc.)
- [ ] **API endpoints** respond correctly (test 10+ endpoints)
- [ ] **WebSocket** real-time updates work
- [ ] **GNN training** completes without errors
- [ ] **Performance** is acceptable (response times < 200ms)
- [ ] **No errors** in logs

---

## 🔄 Rollback Plan

If migration fails:

```bash
# 1. Stop PostgreSQL
docker compose down

# 2. Restore MariaDB configuration
git checkout mariadb-baseline-$(date +%Y%m%d)

# 3. Restore data (if needed)
docker compose up -d db
docker compose exec -T db mysql -u root -p < backups/mariadb_backup.sql

# 4. Restart services
docker compose up -d

# 5. Verify
curl http://localhost:8000/health
```

---

## 📊 Migration Timeline

```
Day 1: Preparation      [████████████░░░░░░░░░░░░] 50% complete
Day 2: Migration        [░░░░░░░░░░░░░░░░░░░░░░░░] 0% complete
Day 3: Testing          [░░░░░░░░░░░░░░░░░░░░░░░░] 0% complete
Day 4: Production       [░░░░░░░░░░░░░░░░░░░░░░░░] 0% complete

Current Status: Ready to begin Day 1
```

---

## 🎯 Next Steps

1. **Read** [MARIADB_TO_POSTGRESQL_MIGRATION_PLAN.md](MARIADB_TO_POSTGRESQL_MIGRATION_PLAN.md) in full
2. **Schedule** 3-4 days for migration work
3. **Backup** current database
4. **Start** Day 1: Preparation (follow this guide)
5. **Test** thoroughly before production deployment

---

## 📞 Support

- **Full Migration Plan**: [MARIADB_TO_POSTGRESQL_MIGRATION_PLAN.md](MARIADB_TO_POSTGRESQL_MIGRATION_PLAN.md)
- **PostgreSQL Docs**: https://www.postgresql.org/docs/16/
- **SQLAlchemy + PostgreSQL**: https://docs.sqlalchemy.org/en/20/dialects/postgresql.html

---

**Ready to begin?** Start with the **Quick Start** section above! 🚀
