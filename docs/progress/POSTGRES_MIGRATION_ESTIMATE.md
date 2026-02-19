# PostgreSQL Migration Effort Estimate

**Date**: 2026-01-15
**Current DB**: MariaDB 10.11
**Target DB**: PostgreSQL 15+

---

## Executive Summary

Converting from MariaDB to PostgreSQL is **MODERATE EFFORT** (2-4 days for experienced developer).

**Complexity Rating**: 🟡 **MEDIUM** (6/10)

**Recommendation**:
- ✅ **Worth doing** if you need PostgreSQL-specific features (JSONB, array operations, full-text search, extensions)
- ⚠️ **Not urgent** if MariaDB is working well and you don't need PostgreSQL features
- 🔴 **Consider carefully** if you're on a tight deadline - focus on features first

---

## Effort Breakdown

| Component | Effort | Complexity | Risk |
|-----------|--------|------------|------|
| 1. Docker Configuration | 1-2 hours | 🟢 LOW | 🟢 LOW |
| 2. Python Dependencies | 30 min | 🟢 LOW | 🟢 LOW |
| 3. Connection Strings | 1 hour | 🟢 LOW | 🟢 LOW |
| 4. SQLAlchemy Models | 2-3 hours | 🟡 MEDIUM | 🟡 MEDIUM |
| 5. Raw SQL Queries | 3-4 hours | 🟡 MEDIUM | 🟡 MEDIUM |
| 6. Migration Scripts | 4-6 hours | 🟡 MEDIUM | 🔴 HIGH |
| 7. Testing & Validation | 4-6 hours | 🟡 MEDIUM | 🔴 HIGH |
| 8. Data Migration | 2-4 hours | 🟡 MEDIUM | 🔴 HIGH |
| **TOTAL** | **17-26 hours** | 🟡 MEDIUM | 🟡 MEDIUM |

**Estimated Time**: 2-4 days for experienced developer, 4-7 days for less experienced

---

## Current State Analysis

### Database Statistics
- **Total Tables**: 69 tables
- **SQLAlchemy Models**: 21 Python files
- **MySQL-Specific Code Locations**: 14 references
- **MySQL Dialect Imports**: 1 (in aws_sc_planning.py)
- **Raw SQL Usage**: 8 files using `text()` queries
- **Migration Scripts**: 1 SQL file (310 lines, Sprint 4)

### MySQL-Specific Features In Use

#### 1. Data Types
```sql
✓ INT(11) - needs conversion to INTEGER
✓ TINYINT(1) - needs conversion to BOOLEAN
✓ ENUM(...) - needs conversion to CHECK constraint or custom type
✓ DECIMAL(10,2) - compatible (no change needed)
✓ JSON - compatible (but PostgreSQL has JSONB which is better)
✓ LONGTEXT - needs conversion to TEXT
```

#### 2. Syntax Differences
```sql
✓ AUTO_INCREMENT → SERIAL or GENERATED ALWAYS AS IDENTITY
✓ CURRENT_TIMESTAMP → CURRENT_TIMESTAMP (compatible)
✓ ON UPDATE CURRENT_TIMESTAMP → trigger needed
✓ ENGINE=InnoDB → not needed (PostgreSQL doesn't use storage engines)
✓ COLLATE=utf8mb4_unicode_ci → not needed (PostgreSQL uses LC_COLLATE)
✓ ON DUPLICATE KEY UPDATE → needs conversion to ON CONFLICT ... DO UPDATE
```

#### 3. Python Code
```python
# Connection strings
mysql+pymysql:// → postgresql+psycopg://
mysql+aiomysql:// → postgresql+asyncpg://

# Dialects
from sqlalchemy.dialects.mysql import DECIMAL, JSON
→ from sqlalchemy.dialects.postgresql import JSONB, UUID
```

---

## Detailed Migration Steps

### Step 1: Docker Configuration (1-2 hours)

**Files to modify**:
- `docker-compose.yml` - Replace MariaDB with PostgreSQL
- `docker-compose.dev.yml`
- `docker-compose.prod.yml`
- `docker-compose.db.yml`
- `.env` - Update environment variables

**Changes**:
```yaml
# OLD
db:
  image: mariadb:10.11
  environment:
    MARIADB_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
    MYSQL_DATABASE: ${MYSQL_DATABASE}
    MYSQL_USER: ${MYSQL_USER}
    MYSQL_PASSWORD: ${MYSQL_PASSWORD}
  healthcheck:
    test: ["CMD", "mysqladmin", "ping"]

# NEW
db:
  image: postgres:15-alpine
  environment:
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    POSTGRES_DB: ${POSTGRES_DB}
    POSTGRES_USER: ${POSTGRES_USER}
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
```

**Environment Variables** (.env):
```bash
# OLD
MYSQL_ROOT_PASSWORD=change-me-root
MYSQL_USER=beer_user
MYSQL_PASSWORD=change-me-user
MYSQL_DATABASE=beer_game
DATABASE_URL=mysql+pymysql://beer_user:change-me-user@db:3306/beer_game?charset=utf8mb4

# NEW
POSTGRES_PASSWORD=change-me-password
POSTGRES_USER=beer_user
POSTGRES_DB=beer_game
DATABASE_URL=postgresql+psycopg://beer_user:change-me-password@db:5432/beer_game
```

**Effort**: 1-2 hours
**Risk**: 🟢 LOW - Straightforward configuration changes

---

### Step 2: Python Dependencies (30 minutes)

**Files to modify**:
- `backend/requirements.txt`
- `backend/pyproject.toml` (if exists)

**Changes**:
```txt
# REMOVE
pymysql
aiomysql
mysqlclient

# ADD
psycopg[binary]>=3.1.0
asyncpg>=0.29.0
```

**Commands**:
```bash
cd backend
pip uninstall pymysql aiomysql mysqlclient
pip install psycopg[binary] asyncpg
```

**Effort**: 30 minutes
**Risk**: 🟢 LOW - Simple dependency swap

---

### Step 3: Connection Strings (1 hour)

**Files to modify** (14 locations):
- `backend/app/db/session.py` (2 changes)
- `backend/app/db/init_db.py` (4 changes)
- `backend/app/core/db_urls.py` (4 changes)
- `backend/app/core/config.py` (1 change)

**Example Changes**:

`backend/app/db/session.py`:
```python
# OLD
async_database_uri = raw_database_uri.replace("mysql+pymysql://", "mysql+aiomysql://", 1)

# NEW
async_database_uri = raw_database_uri.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
```

`backend/app/core/db_urls.py`:
```python
# OLD
def _mysql_url(*, driver: str, user: str, password: str, host: str, port: int, db: str) -> str:
    return f"mysql+{driver}://{user}:{password}@{host}:{port}/{db}?charset=utf8mb4"

driver = "pymysql"

# NEW
def _postgres_url(*, driver: str, user: str, password: str, host: str, port: int, db: str) -> str:
    return f"postgresql+{driver}://{user}:{password}@{host}:{port}/{db}"

driver = "psycopg"
```

**Effort**: 1 hour
**Risk**: 🟢 LOW - Find and replace with testing

---

### Step 4: SQLAlchemy Models (2-3 hours)

**Files to review** (21 model files):
- Most SQLAlchemy types are database-agnostic
- Only 1 file uses MySQL-specific dialect: `backend/app/models/aws_sc_planning.py`

**Changes needed**:

`backend/app/models/aws_sc_planning.py`:
```python
# OLD
from sqlalchemy.dialects.mysql import DECIMAL, JSON

# NEW
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Numeric
# Use JSONB instead of JSON (faster, supports indexing)
# Use Numeric instead of DECIMAL (same thing in PostgreSQL)
```

**Potential Issues**:
- **TINYINT(1) for booleans**: SQLAlchemy's `Boolean` type will handle this automatically
- **ENUM types**: SQLAlchemy's `Enum` type will handle this automatically (creates CHECK constraint)
- **JSON columns**: Consider upgrading to JSONB for better performance
- **Auto-increment IDs**: SQLAlchemy handles this automatically with `Integer, primary_key=True`

**Effort**: 2-3 hours (review all 21 files, modify 1-2)
**Risk**: 🟡 MEDIUM - Mostly automatic, but needs careful testing

---

### Step 5: Raw SQL Queries (3-4 hours)

**Files with raw SQL** (8 files using `text()` queries):
- Need to find and audit each usage
- Convert MySQL-specific syntax to PostgreSQL

**Common Conversions**:

1. **String Concatenation**:
```sql
-- MySQL
CONCAT(a, b, c)

-- PostgreSQL
a || b || c
```

2. **Date Functions**:
```sql
-- MySQL
NOW(), CURDATE(), DATE_ADD(date, INTERVAL 1 DAY)

-- PostgreSQL
CURRENT_TIMESTAMP, CURRENT_DATE, date + INTERVAL '1 day'
```

3. **LIMIT with OFFSET**:
```sql
-- MySQL & PostgreSQL (same)
LIMIT 10 OFFSET 20
```

4. **String Functions**:
```sql
-- MySQL
SUBSTRING(str, 1, 10)

-- PostgreSQL
SUBSTR(str, 1, 10)
```

5. **Auto-increment**:
```sql
-- MySQL
SELECT LAST_INSERT_ID()

-- PostgreSQL
RETURNING id
```

**Example - optimization.py** (lines 169-209):
```python
# Current - uses raw SQL with text()
query = text("""
    SELECT current_round
    FROM games
    WHERE id = :game_id
""")

# This is already PostgreSQL-compatible! ✅
# Most basic SELECT queries work in both databases
```

**Effort**: 3-4 hours (find all raw SQL, test each query)
**Risk**: 🟡 MEDIUM - Depends on complexity of raw SQL

---

### Step 6: Migration Scripts (4-6 hours) 🔴 HIGH RISK

**Files to convert**:
- `backend/migrations/sprint4_a2a_features.sql` (310 lines)
- Any other SQL scripts in init or seed files

**Major Conversions Needed**:

#### 1. AUTO_INCREMENT → SERIAL
```sql
-- MySQL
CREATE TABLE users (
    id INT PRIMARY KEY AUTO_INCREMENT
);

-- PostgreSQL (Option 1: SERIAL)
CREATE TABLE users (
    id SERIAL PRIMARY KEY
);

-- PostgreSQL (Option 2: IDENTITY - recommended)
CREATE TABLE users (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY
);
```

#### 2. ENUM Types
```sql
-- MySQL
negotiation_type ENUM('order_adjustment', 'lead_time', 'inventory_share') NOT NULL

-- PostgreSQL (Option 1: CREATE TYPE)
CREATE TYPE negotiation_type_enum AS ENUM ('order_adjustment', 'lead_time', 'inventory_share');
negotiation_type negotiation_type_enum NOT NULL

-- PostgreSQL (Option 2: CHECK constraint)
negotiation_type VARCHAR(50) NOT NULL,
CONSTRAINT chk_negotiation_type CHECK (negotiation_type IN ('order_adjustment', 'lead_time', 'inventory_share'))
```

#### 3. ON UPDATE CURRENT_TIMESTAMP
```sql
-- MySQL
updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP

-- PostgreSQL (needs trigger)
updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

-- Create trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger
CREATE TRIGGER update_visibility_permissions_updated_at
    BEFORE UPDATE ON visibility_permissions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

#### 4. ON DUPLICATE KEY UPDATE
```sql
-- MySQL
INSERT INTO schema_migrations (version, description, executed_at)
VALUES ('sprint4_a2a_features', 'Sprint 4 features', NOW())
ON DUPLICATE KEY UPDATE executed_at = NOW()

-- PostgreSQL
INSERT INTO schema_migrations (version, description, executed_at)
VALUES ('sprint4_a2a_features', 'Sprint 4 features', CURRENT_TIMESTAMP)
ON CONFLICT (version) DO UPDATE SET executed_at = CURRENT_TIMESTAMP
```

#### 5. Storage Engine & Charset
```sql
-- MySQL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- PostgreSQL (remove entirely)
);
```

#### 6. INT Sizes
```sql
-- MySQL
id BIGINT PRIMARY KEY AUTO_INCREMENT
suggestion_id INT NOT NULL

-- PostgreSQL
id BIGSERIAL PRIMARY KEY  -- or BIGINT GENERATED ALWAYS AS IDENTITY
suggestion_id INTEGER NOT NULL
```

**Effort**: 4-6 hours (convert 310 lines + test thoroughly)
**Risk**: 🔴 HIGH - SQL syntax differences can cause subtle bugs

---

### Step 7: Testing & Validation (4-6 hours) 🔴 HIGH RISK

**Test Checklist**:

1. **Schema Creation**:
   - [ ] All 69 tables created successfully
   - [ ] All foreign keys working
   - [ ] All indexes created
   - [ ] All triggers working
   - [ ] All views created

2. **Application Startup**:
   - [ ] Backend starts without errors
   - [ ] Database connection pool established
   - [ ] All endpoints register correctly

3. **CRUD Operations**:
   - [ ] Create records (INSERT)
   - [ ] Read records (SELECT)
   - [ ] Update records (UPDATE)
   - [ ] Delete records (DELETE)
   - [ ] Verify auto-increment/SERIAL IDs

4. **Feature Testing**:
   - [ ] User authentication works
   - [ ] Game creation works
   - [ ] Round progression works
   - [ ] AI suggestions work
   - [ ] Pattern analysis works
   - [ ] Negotiations work
   - [ ] Global optimization works
   - [ ] Visibility dashboard works

5. **Data Integrity**:
   - [ ] Foreign key constraints enforced
   - [ ] ENUM/CHECK constraints enforced
   - [ ] NOT NULL constraints enforced
   - [ ] UNIQUE constraints enforced
   - [ ] Default values working

6. **Performance**:
   - [ ] Query performance acceptable
   - [ ] Connection pool not exhausted
   - [ ] No N+1 query issues
   - [ ] Indexes being used

**Effort**: 4-6 hours (comprehensive testing)
**Risk**: 🔴 HIGH - Hidden bugs may appear in production

---

### Step 8: Data Migration (2-4 hours) 🔴 HIGH RISK

**If you have existing data** to migrate from MariaDB to PostgreSQL:

**Tools**:
1. **pgLoader** (recommended) - automatic migration tool
2. **mysqldump + manual conversion**
3. **Python script using SQLAlchemy**

**pgLoader Approach** (easiest):
```bash
# Install pgLoader
apt-get install pgloader  # Ubuntu/Debian
brew install pgloader      # macOS

# Create migration config
cat > migration.load <<EOF
LOAD DATABASE
    FROM mysql://beer_user:change-me-user@localhost/beer_game
    INTO postgresql://beer_user:change-me-password@localhost/beer_game

WITH include drop, create tables, create indexes, reset sequences,
     workers = 4, concurrency = 1

SET maintenance_work_mem to '512MB',
    work_mem to '128MB'

CAST type tinyint to boolean drop typemod using tinyint-to-boolean,
     type datetime to timestamptz drop default drop not null using zero-dates-to-null,
     type json to jsonb drop typemod

ALTER SCHEMA 'beer_game' RENAME TO 'public'
;
EOF

# Run migration
pgloader migration.load
```

**Manual Approach**:
```bash
# 1. Export MySQL data
mysqldump -u beer_user -p beer_game > beer_game_dump.sql

# 2. Convert SQL syntax (manual or script)
# - Replace AUTO_INCREMENT with SERIAL
# - Replace ENUM with CHECK constraints
# - Remove ENGINE=InnoDB and CHARSET clauses
# - Fix date/time functions
# - Fix string functions

# 3. Import to PostgreSQL
psql -U beer_user -d beer_game < beer_game_converted.sql
```

**Python Script Approach**:
```python
# Read from MySQL, write to PostgreSQL
from sqlalchemy import create_engine
import pandas as pd

mysql_engine = create_engine('mysql+pymysql://...')
postgres_engine = create_engine('postgresql+psycopg://...')

# For each table
for table_name in tables:
    df = pd.read_sql_table(table_name, mysql_engine)
    df.to_sql(table_name, postgres_engine, if_exists='append', index=False)
```

**Effort**: 2-4 hours (depends on data volume)
**Risk**: 🔴 HIGH - Data corruption or loss possible

---

## Benefits of PostgreSQL

### Why migrate?

1. **Better JSON Support**: JSONB is faster and supports indexing
2. **Advanced Features**: Array types, hstore, full-text search, CTEs
3. **Extensions**: PostGIS (spatial), TimescaleDB (time-series), pgvector (ML)
4. **Better Standards Compliance**: More SQL standard compliant
5. **Superior Concurrency**: MVCC implementation (no table locks)
6. **Window Functions**: More powerful analytics
7. **Better Full-Text Search**: Built-in tsvector/tsquery
8. **Community**: Larger open-source community
9. **Performance**: Generally faster for complex queries
10. **Ecosystem**: Better tooling (pgAdmin, DataGrip integration)

### When NOT to migrate:

1. ❌ You need MySQL-specific features (spatial extensions specific to MySQL)
2. ❌ Your team only knows MySQL and doesn't want to learn PostgreSQL
3. ❌ You're on a tight deadline and can't afford 2-4 days
4. ❌ Your queries are all simple CRUD (no benefit)
5. ❌ You're already using MariaDB-specific optimizations

---

## Recommended Approach

### Option 1: Full Migration (Recommended for new projects)

**Timeline**: 2-4 days
**When**: Starting fresh or major refactor

1. Create new PostgreSQL container
2. Update Python dependencies
3. Convert connection strings
4. Review/update SQLAlchemy models
5. Convert migration scripts
6. Test thoroughly
7. Deploy to staging
8. Test in staging for 1 week
9. Deploy to production

### Option 2: Dual Support (Recommended for existing projects)

**Timeline**: 3-5 days
**When**: Need to support both databases

1. Use SQLAlchemy abstractions (avoid raw SQL)
2. Create separate migration scripts for each DB
3. Test on both databases in CI/CD
4. Allow database selection via environment variable
5. Migrate clients gradually

### Option 3: Stay with MariaDB (Recommended if it works)

**Timeline**: 0 days
**When**: No compelling reason to switch

- MariaDB 10.11 is excellent
- No performance issues
- Team knows MySQL well
- Focus on features, not infrastructure

---

## Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Data loss during migration | 🔴 HIGH | 🟡 MEDIUM | Backup before migration, test with copy first |
| Hidden SQL incompatibilities | 🟡 MEDIUM | 🔴 HIGH | Comprehensive testing, gradual rollout |
| Performance regression | 🟡 MEDIUM | 🟡 MEDIUM | Load testing, query profiling, indexing |
| Team unfamiliarity with PostgreSQL | 🟢 LOW | 🔴 HIGH | Training, documentation, PostgreSQL expert on call |
| Downtime during migration | 🔴 HIGH | 🟢 LOW | Blue-green deployment, database replication |
| Trigger behavior differences | 🟡 MEDIUM | 🟡 MEDIUM | Test all triggers thoroughly |

---

## Cost Analysis

### Developer Time
- **Junior Dev**: 4-7 days × $300/day = **$1,200 - $2,100**
- **Mid-Level Dev**: 3-5 days × $500/day = **$1,500 - $2,500**
- **Senior Dev**: 2-4 days × $800/day = **$1,600 - $3,200**

### Ongoing Benefits
- **Performance**: 10-30% faster complex queries
- **Scalability**: Better handling of concurrent writes
- **Features**: Access to PostgreSQL extensions
- **Maintenance**: Potentially easier maintenance (better tooling)

### Return on Investment
- **Break-even**: 6-12 months if you use PostgreSQL features
- **No ROI**: If you stay with simple CRUD operations

---

## Recommendation

### ✅ **Migrate IF**:
- Starting a new phase of development
- Need PostgreSQL-specific features (JSONB, arrays, extensions)
- Planning for high concurrency
- Want better JSON performance
- Team wants to learn PostgreSQL
- Have 2-4 days available

### ⚠️ **Consider carefully IF**:
- Currently using MariaDB-specific features
- Team is unfamiliar with PostgreSQL
- On a tight deadline for Sprint 5+
- MariaDB is working well

### 🔴 **DON'T migrate IF**:
- No clear benefit identified
- Less than 1 week available
- In the middle of critical features (Sprint 4 just completed)
- No PostgreSQL expertise available

---

## Conclusion

**Effort**: 2-4 days (17-26 hours)
**Complexity**: 🟡 MEDIUM (6/10)
**Risk**: 🟡 MEDIUM
**Cost**: $1,600 - $3,200 (senior dev)

**My Recommendation**:
- **Wait until after Sprint 5-6** to avoid disrupting feature development
- **Plan the migration** for a dedicated sprint or maintenance window
- **Use pgLoader** for data migration to minimize manual work
- **Test thoroughly** in staging before production
- **Consider it a good investment** if you plan to use PostgreSQL features

**Alternative**: Stay with MariaDB - it's working well, and you can focus on delivering features. PostgreSQL migration can always happen later if needed.

---

**Questions to ask yourself**:
1. Do you need any PostgreSQL-specific features?
2. Is MariaDB causing any problems?
3. Do you have 2-4 days to spare?
4. Does your team know PostgreSQL?
5. Are you willing to take the risk of migration bugs?

If you answered "no" to 3+ questions, **stick with MariaDB** for now.

---

**Next Steps** (if you decide to migrate):
1. Create a detailed migration plan
2. Set up PostgreSQL in development
3. Convert one migration script as a test
4. Test thoroughly
5. Convert remaining code
6. Test again
7. Deploy to staging
8. Monitor for issues
9. Deploy to production

