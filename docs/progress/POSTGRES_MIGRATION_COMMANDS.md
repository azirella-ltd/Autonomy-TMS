# PostgreSQL Migration - Command Reference

**Quick reference for Day 2-4 migration tasks**

---

## 📋 Day 2: Data Migration Commands

### Step 1: Backup MariaDB (CRITICAL - Do First!)

```bash
# Create backup directory
mkdir -p backups/mariadb_$(date +%Y%m%d)

# Full database backup with mysqldump
docker compose exec db mysqldump \
  -u root -p \
  --databases beer_game \
  --single-transaction \
  --quick \
  --lock-tables=false \
  --routines \
  --triggers \
  --events \
  > backups/mariadb_$(date +%Y%m%d)/beer_game_full_backup.sql

# Verify backup was created
ls -lh backups/mariadb_$(date +%Y%m%d)/
```

### Step 2: Build New Containers

```bash
# Rebuild backend with PostgreSQL dependencies
docker compose build backend

# Verify no errors in build
docker compose build backend 2>&1 | tee build.log
grep -i error build.log
```

### Step 3: Start PostgreSQL

```bash
# Start only the database service
docker compose up -d db

# Watch logs until you see "database system is ready to accept connections"
docker compose logs -f db

# Check database is healthy (Ctrl+C to exit logs, then run:)
docker compose ps db
# Should show: Up (healthy)
```

### Step 4: Test PostgreSQL Connection

```bash
# Test connection from host
docker compose exec db pg_isready -U beer_user -d beer_game

# Connect to database
docker compose exec db psql -U beer_user -d beer_game

# Inside psql, verify database:
\l              # List databases
\dt             # List tables (should be empty)
\q              # Quit
```

### Step 5: Create Database Schema

**Option A: Via SQLAlchemy (Recommended)**
```bash
# Run init_db.py to create all tables
docker compose exec backend python -m app.db.init_db

# Verify tables were created
docker compose exec db psql -U beer_user -d beer_game -c "
SELECT COUNT(*) AS table_count
FROM information_schema.tables
WHERE table_schema='public';
"
# Should show: 97
```

**Option B: Via Alembic**
```bash
# Run all migrations
docker compose exec backend alembic upgrade head

# Check migration status
docker compose exec backend alembic current

# Verify tables
docker compose exec db psql -U beer_user -d beer_game -c "\dt"
```

### Step 6: Export Data from MariaDB

If MariaDB is still running (separate container):

```bash
# Export only data (no schema)
docker compose exec old_mariadb mysqldump \
  -u root -p \
  --no-create-info \
  --complete-insert \
  --skip-extended-insert \
  beer_game \
  > backups/mariadb_$(date +%Y%m%d)/beer_game_data_only.sql
```

Or use the backup from Step 1.

### Step 7: Convert SQL Format (if needed)

```bash
# Create conversion script
cat > scripts/convert_to_postgres.py << 'EOF'
#!/usr/bin/env python3
import re
import sys

def convert_dump(input_file, output_file):
    with open(input_file, 'r', encoding='utf8') as f:
        content = f.read()

    # Remove MySQL-specific syntax
    content = re.sub(r'ENGINE=InnoDB', '', content)
    content = re.sub(r'DEFAULT CHARSET=\w+', '', content)
    content = re.sub(r'AUTO_INCREMENT=\d+', '', content)
    content = content.replace('`', '"')

    # Convert TINYINT to SMALLINT
    content = re.sub(r'TINYINT\(\d+\)', 'SMALLINT', content)

    with open(output_file, 'w', encoding='utf8') as f:
        f.write(content)

    print(f"Converted {input_file} -> {output_file}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python convert_to_postgres.py input.sql output.sql")
        sys.exit(1)
    convert_dump(sys.argv[1], sys.argv[2])
EOF

chmod +x scripts/convert_to_postgres.py

# Run conversion
python3 scripts/convert_to_postgres.py \
  backups/mariadb_$(date +%Y%m%d)/beer_game_data_only.sql \
  backups/postgres_data_converted.sql
```

### Step 8: Import Data into PostgreSQL

```bash
# Import converted data
docker compose exec -T db psql -U beer_user -d beer_game < backups/postgres_data_converted.sql

# Check for errors
docker compose logs db --tail 100 | grep ERROR
```

### Step 9: Reset Sequences

```bash
# Reset all sequences to correct values
docker compose exec db psql -U beer_user -d beer_game << 'EOF'
DO $$
DECLARE
    seq_record RECORD;
    max_id INTEGER;
BEGIN
    FOR seq_record IN
        SELECT
            n.nspname AS schema,
            c.relname AS table_name,
            a.attname AS column_name,
            s.relname AS sequence_name
        FROM pg_class c
        JOIN pg_attribute a ON a.attrelid = c.oid
        JOIN pg_depend d ON d.refobjid = c.oid AND d.refobjsubid = a.attnum
        JOIN pg_class s ON s.oid = d.objid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND s.relkind = 'S'
          AND n.nspname = 'public'
    LOOP
        EXECUTE format('SELECT COALESCE(MAX(%I), 0) + 1 FROM %I.%I',
                       seq_record.column_name,
                       seq_record.schema,
                       seq_record.table_name)
        INTO max_id;

        EXECUTE format('SELECT setval(%L, %s, false)',
                       seq_record.schema || '.' || seq_record.sequence_name,
                       max_id);

        RAISE NOTICE 'Reset % to %', seq_record.sequence_name, max_id;
    END LOOP;
END $$;
EOF
```

### Step 10: Validate Data

```bash
# Row counts for critical tables
docker compose exec db psql -U beer_user -d beer_game << 'EOF'
SELECT 'users' AS table_name, COUNT(*) AS row_count FROM users
UNION ALL
SELECT 'groups', COUNT(*) FROM groups
UNION ALL
SELECT 'games', COUNT(*) FROM games
UNION ALL
SELECT 'players', COUNT(*) FROM players
UNION ALL
SELECT 'rounds', COUNT(*) FROM rounds
UNION ALL
SELECT 'supply_chain_configs', COUNT(*) FROM supply_chain_configs
ORDER BY table_name;
EOF

# Check for orphaned records
docker compose exec db psql -U beer_user -d beer_game << 'EOF'
-- Orphaned players
SELECT 'orphaned_players' AS check_name,
       COUNT(*) AS count
FROM players
WHERE game_id NOT IN (SELECT id FROM games);

-- Orphaned rounds
SELECT 'orphaned_rounds',
       COUNT(*)
FROM rounds
WHERE game_id NOT IN (SELECT id FROM games);
EOF
```

---

## 🧪 Day 3: Testing Commands

### Start Full Stack

```bash
# Start all services
docker compose up -d

# Wait for all services to be healthy
docker compose ps

# Check backend logs
docker compose logs backend --tail 50
```

### Backend Health Check

```bash
# Test health endpoint
curl http://localhost:8000/health

# Expected output:
# {"status":"healthy","database":"connected"}
```

### Test Authentication

```bash
# Login
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "systemadmin@autonomy.ai",
    "password": "Autonomy@2026"
  }' | jq -r '.access_token')

echo "Token: $TOKEN"

# Test authenticated endpoint
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/users/me | jq
```

### Test Game Creation

```bash
# Create a test game
GAME_ID=$(curl -s -X POST http://localhost:8000/api/v1/agent-games/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "PostgreSQL Test Game",
    "config_name": "Default TBG",
    "max_rounds": 24
  }' | jq -r '.id')

echo "Game ID: $GAME_ID"

# Start the game
curl -s -X POST http://localhost:8000/api/v1/agent-games/$GAME_ID/start \
  -H "Authorization: Bearer $TOKEN" | jq

# Play 5 rounds
for i in {1..5}; do
  echo "Playing round $i..."
  curl -s -X POST http://localhost:8000/api/v1/agent-games/$GAME_ID/play-round \
    -H "Authorization: Bearer $TOKEN" | jq '.round_number'
  sleep 2
done

# Check game state
curl -s http://localhost:8000/api/v1/agent-games/$GAME_ID/state \
  -H "Authorization: Bearer $TOKEN" | jq
```

### Database Performance

```bash
# Cache hit ratio (should be > 95%)
docker compose exec db psql -U beer_user -d beer_game << 'EOF'
SELECT
  SUM(heap_blks_hit) / (SUM(heap_blks_hit) + SUM(heap_blks_read)) * 100
  AS cache_hit_ratio
FROM pg_statio_user_tables;
EOF

# Active connections
docker compose exec db psql -U beer_user -d beer_game << 'EOF'
SELECT COUNT(*), state
FROM pg_stat_activity
WHERE datname='beer_game'
GROUP BY state;
EOF

# Slow queries (if pg_stat_statements is enabled)
docker compose exec db psql -U beer_user -d beer_game << 'EOF'
SELECT query, calls, mean_exec_time, max_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
EOF
```

---

## 🔍 Monitoring & Debugging

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f db
docker compose logs -f pgadmin

# Last N lines
docker compose logs backend --tail 100

# Search logs for errors
docker compose logs backend | grep -i error
docker compose logs db | grep -i error
```

### Database Queries

```bash
# Connect to database
docker compose exec db psql -U beer_user -d beer_game

# Useful queries inside psql:
\dt                    # List all tables
\d+ table_name         # Describe table structure
\di                    # List all indexes
\df                    # List all functions
\l                     # List all databases

SELECT version();      # PostgreSQL version
SELECT current_database();
SELECT current_user;

# Check table sizes
SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size('public.'||tablename)) AS size
FROM pg_tables
WHERE schemaname='public'
ORDER BY pg_total_relation_size('public.'||tablename) DESC
LIMIT 10;
```

### pgAdmin Access

```bash
# Access pgAdmin web interface
open http://localhost:5050

# Or if on remote server:
# http://SERVER_IP:5050

# Login credentials (from .env):
# Email: admin@autonomy.ai
# Password: admin

# Add server in pgAdmin:
# Host: db
# Port: 5432
# Database: beer_game
# Username: beer_user
# Password: change-me-user (or your password from .env)
```

---

## 🔄 Rollback Commands

### Quick Rollback to MariaDB

```bash
# Stop PostgreSQL stack
docker compose down

# Checkout previous commit
git checkout mariadb-baseline-$(date +%Y%m%d)

# Or just revert docker-compose changes
git checkout HEAD~1 docker-compose.yml
git checkout HEAD~1 .env

# Restore MariaDB
docker compose up -d

# Verify MariaDB is running
docker compose exec db mysql -u root -p -e "SHOW DATABASES;"
```

### Full Rollback with Data Restore

```bash
# Stop all services
docker compose down

# Restore MariaDB configuration
git checkout mariadb-baseline-$(date +%Y%m%d)

# Start MariaDB
docker compose up -d db

# Restore data from backup
docker compose exec -T db mysql -u root -p < backups/mariadb_20260116/beer_game_full_backup.sql

# Start all services
docker compose up -d

# Test
curl http://localhost:8000/health
```

---

## 📊 Validation Scripts

### Create Validation Script

```bash
cat > scripts/validate_migration.sh << 'EOF'
#!/bin/bash

echo "PostgreSQL Migration Validation"
echo "================================"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

pass=0
fail=0

# Test 1: Database connection
echo -n "Test 1: Database connection... "
if docker compose exec db pg_isready -U beer_user -d beer_game > /dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC}"
    ((pass++))
else
    echo -e "${RED}FAIL${NC}"
    ((fail++))
fi

# Test 2: Table count
echo -n "Test 2: Table count (97 tables)... "
table_count=$(docker compose exec db psql -U beer_user -d beer_game -tAc \
  "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';")
if [ "$table_count" -eq 97 ]; then
    echo -e "${GREEN}PASS${NC} ($table_count tables)"
    ((pass++))
else
    echo -e "${RED}FAIL${NC} (found $table_count, expected 97)"
    ((fail++))
fi

# Test 3: Backend health
echo -n "Test 3: Backend health... "
if curl -sf http://localhost:8000/health | grep -q "healthy"; then
    echo -e "${GREEN}PASS${NC}"
    ((pass++))
else
    echo -e "${RED}FAIL${NC}"
    ((fail++))
fi

# Test 4: Authentication
echo -n "Test 4: Authentication... "
token=$(curl -sf -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"systemadmin@autonomy.ai","password":"Autonomy@2026"}' \
  | jq -r '.access_token')
if [ -n "$token" ] && [ "$token" != "null" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((pass++))
else
    echo -e "${RED}FAIL${NC}"
    ((fail++))
fi

# Test 5: User data
echo -n "Test 5: User data exists... "
user_count=$(docker compose exec db psql -U beer_user -d beer_game -tAc \
  "SELECT COUNT(*) FROM users;")
if [ "$user_count" -gt 0 ]; then
    echo -e "${GREEN}PASS${NC} ($user_count users)"
    ((pass++))
else
    echo -e "${RED}FAIL${NC}"
    ((fail++))
fi

echo ""
echo "================================"
echo "Results: ${GREEN}$pass passed${NC}, ${RED}$fail failed${NC}"

if [ $fail -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi
EOF

chmod +x scripts/validate_migration.sh
```

### Run Validation

```bash
./scripts/validate_migration.sh
```

---

## 🎯 Quick Reference

### Common Locations

```bash
# PostgreSQL data
docker volume inspect the_beer_game_postgres_data

# pgAdmin data
docker volume inspect the_beer_game_pgadmin_data

# Backend logs
docker compose logs backend --tail 100

# Database logs
docker compose logs db --tail 100
```

### Useful Docker Commands

```bash
# Restart single service
docker compose restart backend
docker compose restart db

# View service status
docker compose ps

# Remove everything (CAREFUL!)
docker compose down -v  # Removes volumes too!

# Rebuild specific service
docker compose build backend

# Shell into container
docker compose exec backend bash
docker compose exec db bash
```

### Environment Check

```bash
# Check DATABASE_TYPE
grep DATABASE_TYPE .env

# Check PostgreSQL connection string
grep DATABASE_URL .env

# Verify ports
docker compose ps | grep -E "(5432|5050)"
```

---

## 📝 Notes

- **Port 5432**: PostgreSQL database
- **Port 5050**: pgAdmin web interface
- **Port 8000**: Backend API
- **Port 3000**: Frontend (direct)
- **Port 8088**: Nginx proxy

All commands assume you're in the project root directory: `/home/trevor/Projects/The_Beer_Game/`

---

**Quick Start for Day 2**:
```bash
# 1. Backup
mkdir -p backups/mariadb_$(date +%Y%m%d)
# ... (full backup command from Step 1 above)

# 2. Build & Start
docker compose build backend
docker compose up -d db

# 3. Create Schema
docker compose exec backend python -m app.db.init_db

# 4. Validate
docker compose exec db psql -U beer_user -d beer_game -c "\dt"
```

**Status**: Ready for Day 2 execution
