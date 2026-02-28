# MariaDB to PostgreSQL Migration Plan

**Date**: 2026-01-16
**Project**: The Beer Game
**Current Database**: MariaDB 10.11
**Target Database**: PostgreSQL 16
**Estimated Time**: 3-4 days (development + testing)
**Risk Level**: Medium (substantial changes, production data migration required)

---

## Executive Summary

This document provides a comprehensive step-by-step plan to migrate The Beer Game from MariaDB 10.11 to PostgreSQL 16. The migration involves:

- 12 critical files requiring changes
- 17+ Alembic migration files to review
- Docker configuration updates (3 files)
- Python dependencies updates
- Database initialization script rewrites
- Data migration from MariaDB to PostgreSQL
- Comprehensive testing

**Total Changes**: ~45 files, 97 database tables to migrate

---

## Table of Contents

1. [Pre-Migration Checklist](#1-pre-migration-checklist)
2. [Backup Strategy](#2-backup-strategy)
3. [Implementation Phases](#3-implementation-phases)
4. [Detailed Change List](#4-detailed-change-list)
5. [Data Migration Strategy](#5-data-migration-strategy)
6. [Testing Plan](#6-testing-plan)
7. [Rollback Plan](#7-rollback-plan)
8. [Post-Migration Validation](#8-post-migration-validation)
9. [Performance Tuning](#9-performance-tuning)
10. [Known Issues and Workarounds](#10-known-issues-and-workarounds)

---

## 1. Pre-Migration Checklist

### 1.1 Prerequisites

- [ ] **Full database backup** completed and verified
- [ ] **Docker** and **Docker Compose** v2+ installed
- [ ] **Git branch** created for migration work (`git checkout -b postgres-migration`)
- [ ] **Development environment** available for testing
- [ ] **PostgreSQL knowledge** - understand psql, pg_dump, pg_restore
- [ ] **Downtime window** scheduled (if production migration)
- [ ] **Stakeholders** notified of migration timeline

### 1.2 Environment Verification

```bash
# Verify current database status
docker compose ps db
docker compose exec db mysql -u root -p -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='beer_game';"
# Should show: 97 tables

# Check current data volume
docker compose exec db mysql -u root -p beer_game -e "
SELECT
  table_name,
  table_rows,
  ROUND(((data_length + index_length) / 1024 / 1024), 2) AS size_mb
FROM information_schema.tables
WHERE table_schema='beer_game'
ORDER BY (data_length + index_length) DESC
LIMIT 20;
"

# Verify backend is healthy
docker compose ps backend
curl http://localhost:8000/health
```

### 1.3 Dependencies Review

**Current MariaDB Dependencies**:
- `pymysql==1.1.0` - Python MySQL driver
- `aiomysql==0.2.0` - Async MySQL driver
- `mysql-connector-python==8.0.33` - MySQL official connector
- `asyncmy==0.2.7` - Alternative async driver

**Target PostgreSQL Dependencies**:
- `psycopg2-binary==2.9.9` - PostgreSQL driver (or psycopg 3.x)
- `asyncpg==0.29.0` - Async PostgreSQL driver (faster than psycopg async)

---

## 2. Backup Strategy

### 2.1 Full Database Backup

```bash
# Create backup directory
mkdir -p backups/mariadb_$(date +%Y%m%d)

# Export all data with mysqldump
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

# Export schema only (for reference)
docker compose exec db mysqldump \
  -u root -p \
  --no-data \
  --databases beer_game \
  > backups/mariadb_$(date +%Y%m%d)/beer_game_schema_only.sql

# Export data only (for conversion)
docker compose exec db mysqldump \
  -u root -p \
  --no-create-info \
  --complete-insert \
  --skip-extended-insert \
  --databases beer_game \
  > backups/mariadb_$(date +%Y%m%d)/beer_game_data_only.sql

# Verify backup file sizes
ls -lh backups/mariadb_$(date +%Y%m%d)/
```

### 2.2 Export Critical Configuration

```bash
# Backup environment files
cp .env backups/mariadb_$(date +%Y%m%d)/.env.backup
cp backend/alembic.ini backups/mariadb_$(date +%Y%m%d)/alembic.ini.backup

# Backup Docker Compose files
cp docker-compose.yml backups/mariadb_$(date +%Y%m%d)/
cp docker-compose.db.yml backups/mariadb_$(date +%Y%m%d)/
cp docker-compose.prod.yml backups/mariadb_$(date +%Y%m%d)/

# Backup current database config
cp mariadb.cnf backups/mariadb_$(date +%Y%m%d)/
```

### 2.3 Git Snapshot

```bash
# Commit current state before changes
git add -A
git commit -m "Pre-migration snapshot: MariaDB 10.11 baseline"
git tag mariadb-baseline-$(date +%Y%m%d)

# Create migration branch
git checkout -b postgres-migration
```

---

## 3. Implementation Phases

### Phase 1: Preparation (Day 1, 4-6 hours)

**Goal**: Update code and configuration without affecting MariaDB

**Tasks**:
1. Update Python dependencies in `requirements.txt`
2. Update Dockerfiles (system dependencies)
3. Update database connection logic (`db_urls.py`, `session.py`)
4. Update initialization scripts (`init_db.py`, `init_db.sql`)
5. Create PostgreSQL configuration file (`postgresql.conf`)
6. Update Docker Compose files
7. Update environment variables

**Deliverables**:
- All code changes committed
- PostgreSQL Docker service configured (not started)
- Dual-database support (can switch via env vars)

### Phase 2: Database Migration (Day 2, 4-6 hours)

**Goal**: Migrate data from MariaDB to PostgreSQL

**Tasks**:
1. Start PostgreSQL container
2. Create database and user
3. Run Alembic migrations or create schema via SQLAlchemy
4. Convert and import data from MariaDB backup
5. Verify data integrity (row counts, key data validation)
6. Test database connections

**Deliverables**:
- PostgreSQL database with all 97 tables
- All data migrated and verified
- Connection tests passing

### Phase 3: Testing (Day 3, 6-8 hours)

**Goal**: Comprehensive application testing with PostgreSQL

**Tasks**:
1. Backend health checks and API tests
2. Game creation and gameplay testing
3. Agent system testing (all 7 agent types)
4. GNN training and inference testing
5. Authentication and authorization testing
6. WebSocket real-time updates testing
7. Data export/import testing
8. Performance benchmarking

**Deliverables**:
- All 159 API endpoints tested
- No regressions found
- Performance metrics documented

### Phase 4: Production Deployment (Day 4, 2-4 hours)

**Goal**: Deploy to production with PostgreSQL

**Tasks**:
1. Schedule maintenance window
2. Final MariaDB backup
3. Stop services
4. Deploy PostgreSQL configuration
5. Migrate production data
6. Start services with PostgreSQL
7. Smoke tests
8. Monitor for 24 hours

**Deliverables**:
- Production running on PostgreSQL
- Monitoring alerts configured
- Rollback plan ready

---

## 4. Detailed Change List

### 4.1 Python Dependencies (`backend/requirements.txt`)

**Remove**:
```diff
- pymysql==1.1.0
- aiomysql==0.2.0
- asyncmy==0.2.7
- mysql-connector-python==8.0.33
```

**Add**:
```diff
+ psycopg2-binary==2.9.9
+ asyncpg==0.29.0
```

**File**: `/home/trevor/Projects/The_Beer_Game/backend/requirements.txt`

**Lines to change**: 12-15

---

### 4.2 Docker System Dependencies

**File**: `backend/Dockerfile.cpu` (also Dockerfile.gpu, Dockerfile.prod)

**Before** (lines 16-22):
```dockerfile
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    default-mysql-client \
    libmariadb-dev \
    libmariadb-dev-compat \
    && rm -rf /var/lib/apt/lists/*
```

**After**:
```dockerfile
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*
```

**Files to Update**:
- `backend/Dockerfile.cpu`
- `backend/Dockerfile.gpu`
- `backend/Dockerfile.prod`

---

### 4.3 Database Connection Logic (`backend/app/core/db_urls.py`)

**Current Implementation** (lines 24-80):
```python
def _mysql_url(sync: bool = True) -> str:
    """Construct MySQL connection URL from environment variables."""
    host = os.getenv("MARIADB_HOST") or os.getenv("MYSQL_SERVER", "localhost")
    port = int(os.getenv("MARIADB_PORT") or os.getenv("MYSQL_PORT", "3306"))
    database = os.getenv("MARIADB_DATABASE") or os.getenv("MYSQL_DB", "beer_game")
    user = os.getenv("MARIADB_USER") or os.getenv("MYSQL_USER", "beer_user")
    password = os.getenv("MARIADB_PASSWORD") or os.getenv("MYSQL_PASSWORD", "beer_password")

    driver = "pymysql" if sync else "aiomysql"
    charset = "utf8mb4"

    return f"mysql+{driver}://{user}:{password}@{host}:{port}/{database}?charset={charset}"
```

**New Implementation**:
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

def get_database_url(sync: bool = True) -> str:
    """
    Resolve database URL from environment.
    Supports explicit DATABASE_URL or constructs from environment variables.
    Defaults to PostgreSQL.
    """
    # 1. Check for explicit DATABASE_URL
    explicit_url = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI")
    if explicit_url:
        logger.info(f"Using explicit DATABASE_URL: {explicit_url[:30]}...")
        return explicit_url

    # 2. Detect database type from environment
    db_type = os.getenv("DATABASE_TYPE", "postgresql").lower()

    if db_type in ("mysql", "mariadb"):
        logger.info("Using MariaDB/MySQL database")
        return _mysql_url(sync=sync)
    elif db_type == "postgresql":
        logger.info("Using PostgreSQL database")
        return _postgres_url(sync=sync)
    else:
        raise ValueError(f"Unsupported DATABASE_TYPE: {db_type}")

def get_async_database_url() -> str:
    """Get async database URL (asyncpg for PostgreSQL, aiomysql for MySQL)."""
    url = get_database_url(sync=False)

    # Convert sync driver to async driver if needed
    if "postgresql+psycopg2://" in url:
        url = url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    elif "mysql+pymysql://" in url:
        url = url.replace("mysql+pymysql://", "mysql+aiomysql://")

    return url
```

**File**: `/home/trevor/Projects/The_Beer_Game/backend/app/core/db_urls.py`

---

### 4.4 Docker Compose - Database Service

**File**: `docker-compose.yml`

**Before** (lines 104-134):
```yaml
  db:
    image: mariadb:10.11
    container_name: beer_game_mariadb
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: ${MARIADB_ROOT_PASSWORD:-19890617}
      MYSQL_DATABASE: ${MARIADB_DATABASE:-beer_game}
      MYSQL_USER: ${MARIADB_USER:-beer_user}
      MYSQL_PASSWORD: ${MARIADB_PASSWORD:-beer_password}
      MYSQL_INITDB_SKIP_TZINFO: 1
    volumes:
      - mariadb_data:/var/lib/mysql
      - ./mariadb.cnf:/etc/mysql/conf.d/custom.cnf:ro
      - ./init_db.sql:/docker-entrypoint-initdb.d/init_db.sql:ro
    ports:
      - "3306:3306"
    networks:
      - beer_game_network
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-u", "root", "-p${MARIADB_ROOT_PASSWORD:-19890617}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
```

**After**:
```yaml
  db:
    image: postgres:16-alpine
    container_name: beer_game_postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRESQL_DATABASE:-beer_game}
      POSTGRES_USER: ${POSTGRESQL_USER:-beer_user}
      POSTGRES_PASSWORD: ${POSTGRESQL_PASSWORD:-beer_password}
      PGDATA: /var/lib/postgresql/data/pgdata
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./postgresql.conf:/etc/postgresql/postgresql.conf:ro
      - ./init_db_postgres.sql:/docker-entrypoint-initdb.d/init_db.sql:ro
    ports:
      - "5432:5432"
    networks:
      - beer_game_network
    command: postgres -c config_file=/etc/postgresql/postgresql.conf
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRESQL_USER:-beer_user} -d ${POSTGRESQL_DATABASE:-beer_game}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
```

**Volumes Section Update**:
```yaml
volumes:
  postgres_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ${PWD}/data/postgres
```

**Files to Update**:
- `docker-compose.yml`
- `docker-compose.db.yml`
- `docker-compose.prod.yml`

---

### 4.5 Database Initialization SQL

**File**: `init_db_postgres.sql` (NEW)

```sql
-- PostgreSQL Database Initialization Script
-- Replaces: init_db.sql (MariaDB)

-- Create database with UTF8 encoding
-- Note: This may not be needed if POSTGRES_DB is set in environment
-- CREATE DATABASE beer_game
--     ENCODING 'UTF8'
--     LC_COLLATE 'en_US.UTF-8'
--     LC_CTYPE 'en_US.UTF-8'
--     TEMPLATE template0;

-- Grant all privileges on database to user
GRANT ALL PRIVILEGES ON DATABASE beer_game TO beer_user;

-- Connect to beer_game database
\c beer_game

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO beer_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO beer_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO beer_user;

-- Allow user to create tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO beer_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO beer_user;

-- Enable extensions (if needed)
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search
```

**File**: `/home/trevor/Projects/The_Beer_Game/init_db_postgres.sql` (NEW)

---

### 4.6 Database Initialization Script

**File**: `backend/app/db/init_db.py`

**Critical Changes** (lines 47-97):

**Before**:
```python
# Line 47-50: Database URI construction
db_config = {
    'host': os.getenv('MARIADB_HOST', 'localhost'),
    'port': int(os.getenv('MARIADB_PORT', '3306')),
    'user': os.getenv('MARIADB_USER', 'beer_user'),
    'password': os.getenv('MARIADB_PASSWORD', 'beer_password'),
    'database': os.getenv('MARIADB_DATABASE', 'beer_game'),
}

# Line 73: Direct MariaDB connection
root_url = f"mysql+pymysql://root:{ROOT_PASSWORD}@{db_config['host']}:{db_config['port']}"

# Line 91-97: MariaDB-specific SQL
conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
conn.execute(text(f"CREATE USER IF NOT EXISTS '{DB_USER}'@'%' IDENTIFIED BY '{DB_PASSWORD}'"))
conn.execute(text(f"GRANT ALL PRIVILEGES ON `{DB_NAME}`.* TO '{DB_USER}'@'%'"))
conn.execute(text("FLUSH PRIVILEGES"))
```

**After**:
```python
# Line 47-50: Database URI construction (PostgreSQL)
db_config = {
    'host': os.getenv('POSTGRESQL_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRESQL_PORT', '5432')),
    'user': os.getenv('POSTGRESQL_USER', 'beer_user'),
    'password': os.getenv('POSTGRESQL_PASSWORD', 'beer_password'),
    'database': os.getenv('POSTGRESQL_DATABASE', 'beer_game'),
}

# Line 73: PostgreSQL connection (to postgres database)
root_url = f"postgresql+psycopg2://postgres:{ROOT_PASSWORD}@{db_config['host']}:{db_config['port']}/postgres"

# Line 91-97: PostgreSQL-specific SQL
# Check if database exists
result = conn.execute(text(f"SELECT 1 FROM pg_database WHERE datname='{DB_NAME}'"))
if not result.fetchone():
    # Create database (must be outside transaction)
    conn.execute(text("COMMIT"))
    conn.execute(text(f"CREATE DATABASE {DB_NAME} ENCODING 'UTF8'"))

# Check if user exists
result = conn.execute(text(f"SELECT 1 FROM pg_roles WHERE rolname='{DB_USER}'"))
if not result.fetchone():
    conn.execute(text(f"CREATE ROLE {DB_USER} WITH LOGIN PASSWORD '{DB_PASSWORD}'"))

# Grant privileges
conn.execute(text(f"GRANT ALL PRIVILEGES ON DATABASE {DB_NAME} TO {DB_USER}"))
# Note: PostgreSQL doesn't have FLUSH PRIVILEGES
```

**File**: `/home/trevor/Projects/The_Beer_Game/backend/app/db/init_db.py`

---

### 4.7 PostgreSQL Configuration File

**File**: `postgresql.conf` (NEW)

```conf
# PostgreSQL Configuration for The Beer Game
# Replaces: mariadb.cnf

# Connection Settings
listen_addresses = '*'
port = 5432
max_connections = 200
superuser_reserved_connections = 3

# Memory Settings
shared_buffers = 256MB              # Equivalent to innodb_buffer_pool_size
effective_cache_size = 1GB
work_mem = 4MB
maintenance_work_mem = 64MB

# Write Ahead Log (WAL) Settings
wal_buffers = 16MB
checkpoint_completion_target = 0.9

# Query Tuning
random_page_cost = 1.1              # For SSD storage
effective_io_concurrency = 200

# Logging Settings
logging_collector = on
log_directory = 'pg_log'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
log_statement = 'none'              # or 'all' for debugging
log_duration = off
log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '
log_timezone = 'UTC'

# Connection Timeouts
tcp_keepalives_idle = 600           # Equivalent to wait_timeout
tcp_keepalives_interval = 10
tcp_keepalives_count = 5

# Autovacuum Settings
autovacuum = on
autovacuum_max_workers = 3
autovacuum_naptime = 1min

# Locale Settings
datestyle = 'iso, mdy'
timezone = 'UTC'
lc_messages = 'en_US.UTF-8'
lc_monetary = 'en_US.UTF-8'
lc_numeric = 'en_US.UTF-8'
lc_time = 'en_US.UTF-8'
default_text_search_config = 'pg_catalog.english'
```

**File**: `/home/trevor/Projects/The_Beer_Game/postgresql.conf` (NEW)

---

### 4.8 Environment Variables

**File**: `.env`

**Add PostgreSQL Variables**:
```env
# PostgreSQL Configuration (replaces MariaDB)
DATABASE_TYPE=postgresql
POSTGRESQL_HOST=db
POSTGRESQL_PORT=5432
POSTGRESQL_DATABASE=beer_game
POSTGRESQL_USER=beer_user
POSTGRESQL_PASSWORD=beer_password
POSTGRES_PASSWORD=beer_password    # For root user

# Async PostgreSQL
POSTGRESQL_ASYNC_DRIVER=asyncpg

# Connection URL (explicit override)
DATABASE_URL=postgresql+psycopg2://beer_user:beer_password@db:5432/beer_game
ASYNC_DATABASE_URL=postgresql+asyncpg://beer_user:beer_password@db:5432/beer_game

# Legacy MariaDB Variables (keep for backward compat during transition)
# MARIADB_HOST=db
# MARIADB_PORT=3306
# MARIADB_DATABASE=beer_game
# MARIADB_USER=beer_user
# MARIADB_PASSWORD=beer_password
```

**File**: `/home/trevor/Projects/The_Beer_Game/.env`

---

### 4.9 Alembic Configuration

**File**: `backend/alembic.ini`

**Before** (line 58):
```ini
sqlalchemy.url = mysql+pymysql://beer_user:beer_password@localhost:3306/beer_game?charset=utf8mb4
```

**After**:
```ini
sqlalchemy.url = postgresql+psycopg2://beer_user:beer_password@localhost:5432/beer_game
```

**Or use environment variable**:
```ini
# sqlalchemy.url = driver://user:pass@localhost/dbname
# Get from environment instead:
# sqlalchemy.url =
```

**File**: `/home/trevor/Projects/The_Beer_Game/backend/alembic.ini`

---

### 4.10 Alembic Environment Script

**File**: `backend/alembic/env.py`

**Update dialect detection** (add after line 20):

```python
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.db_urls import get_database_url  # Import our helper
from app.models.base import Base  # Import Base with all models

# ... existing code ...

def get_url():
    """Get database URL from environment or config."""
    # Use our centralized URL resolver
    return get_database_url(sync=True)

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()  # Use our helper instead of config.get_main_option
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=False,  # PostgreSQL doesn't need batch mode
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()  # Override with our URL

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=False,  # PostgreSQL doesn't need batch mode
        )

        with context.begin_transaction():
            context.run_migrations()
```

**File**: `/home/trevor/Projects/The_Beer_Game/backend/alembic/env.py`

---

### 4.11 Backend Configuration File

**File**: `backend/app/core/config.py`

**Update Settings class** (add PostgreSQL support):

```python
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Database Configuration
    DATABASE_TYPE: str = "postgresql"  # or "mysql", "mariadb"

    # PostgreSQL
    POSTGRESQL_HOST: str = "localhost"
    POSTGRESQL_PORT: int = 5432
    POSTGRESQL_DATABASE: str = "beer_game"
    POSTGRESQL_USER: str = "beer_user"
    POSTGRESQL_PASSWORD: str = "beer_password"

    # MariaDB (legacy, for backward compat)
    MARIADB_HOST: Optional[str] = None
    MARIADB_PORT: Optional[int] = None
    MARIADB_DATABASE: Optional[str] = None
    MARIADB_USER: Optional[str] = None
    MARIADB_PASSWORD: Optional[str] = None

    # Explicit URL override
    DATABASE_URL: Optional[str] = None
    ASYNC_DATABASE_URL: Optional[str] = None

    # ... rest of settings ...

    class Config:
        env_file = ".env"
        case_sensitive = True
```

**File**: `/home/trevor/Projects/The_Beer_Game/backend/app/core/config.py`

---

### 4.12 Backend Main Application

**File**: `backend/main.py`

**No changes required** - uses `get_database_url()` from `db_urls.py` which we've already updated.

**Verification**:
```python
# Around line 50-60, verify it imports from db_urls:
from app.core.db_urls import get_database_url, get_async_database_url
```

---

## 5. Data Migration Strategy

### 5.1 Export Data from MariaDB

**Step 1: Export Schema and Data**

```bash
# Stop backend to prevent writes during export
docker compose stop backend

# Export full database
docker compose exec db mysqldump \
  -u root -p \
  --databases beer_game \
  --single-transaction \
  --quick \
  --lock-tables=false \
  --routines \
  --triggers \
  --events \
  --complete-insert \
  --hex-blob \
  > backups/beer_game_mariadb_full.sql

# Verify export
ls -lh backups/beer_game_mariadb_full.sql
grep -c "INSERT INTO" backups/beer_game_mariadb_full.sql
```

### 5.2 Convert MariaDB Dump to PostgreSQL Format

**Option A: Manual Conversion Script** (Recommended)

Create `scripts/convert_mariadb_to_postgres.py`:

```python
#!/usr/bin/env python3
"""
Convert MariaDB dump to PostgreSQL-compatible SQL.
"""
import re
import sys

def convert_dump(input_file, output_file):
    """Convert MariaDB SQL dump to PostgreSQL format."""

    with open(input_file, 'r', encoding='utf8') as f:
        content = f.read()

    # Remove MariaDB-specific syntax
    content = re.sub(r'ENGINE=InnoDB', '', content)
    content = re.sub(r'DEFAULT CHARSET=\w+', '', content)
    content = re.sub(r'COLLATE=\w+', '', content)
    content = re.sub(r'AUTO_INCREMENT=\d+', '', content)
    content = re.sub(r'CHARACTER SET \w+', '', content)

    # Convert quotes
    content = content.replace('`', '"')

    # Convert AUTO_INCREMENT to SERIAL
    content = re.sub(
        r'(\w+) int\(\d+\) NOT NULL AUTO_INCREMENT',
        r'\1 SERIAL PRIMARY KEY',
        content
    )

    # Convert TINYINT to SMALLINT
    content = re.sub(r'TINYINT\(\d+\)', 'SMALLINT', content)

    # Convert DATETIME to TIMESTAMP
    content = re.sub(r'DATETIME', 'TIMESTAMP', content)

    # Convert ENGINE and other table options
    content = re.sub(r'\) ENGINE=\w+ .*?;', ');', content)

    # Remove LOCK/UNLOCK TABLES
    content = re.sub(r'LOCK TABLES .*?;', '', content)
    content = re.sub(r'UNLOCK TABLES;', '', content)

    # Convert INSERT statements
    # MariaDB uses single-quote for strings, PostgreSQL same
    # No changes needed for basic inserts

    with open(output_file, 'w', encoding='utf8') as f:
        f.write(content)

    print(f"Converted {input_file} -> {output_file}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python convert_mariadb_to_postgres.py <input.sql> <output.sql>")
        sys.exit(1)

    convert_dump(sys.argv[1], sys.argv[2])
```

**Run Conversion**:
```bash
python scripts/convert_mariadb_to_postgres.py \
  backups/beer_game_mariadb_full.sql \
  backups/beer_game_postgres_converted.sql
```

**Option B: Use pgloader** (Automated)

Install pgloader:
```bash
# Ubuntu/Debian
sudo apt-get install pgloader

# macOS
brew install pgloader
```

Create `pgloader.conf`:
```conf
LOAD DATABASE
  FROM mysql://beer_user:beer_password@localhost:3306/beer_game
  INTO postgresql://beer_user:beer_password@localhost:5432/beer_game

WITH include drop, create tables, create indexes, reset sequences,
     workers = 8, concurrency = 1

SET PostgreSQL PARAMETERS
  maintenance_work_mem to '128MB',
  work_mem to '12MB'

CAST type datetime to timestamptz drop default drop not null using zero-dates-to-null,
     type date drop not null drop default using zero-dates-to-null,
     type tinyint to boolean using tinyint-to-boolean,
     type year to integer

ALTER TABLE NAMES MATCHING ~/_temp$/ RENAME TO ~*_backup;
```

Run pgloader:
```bash
# Start both MariaDB and PostgreSQL
docker compose -f docker-compose.yml up -d db
docker compose -f docker-compose-postgres.yml up -d db_postgres

# Run pgloader
pgloader pgloader.conf
```

### 5.3 Import Data into PostgreSQL

**Method 1: Direct SQL Import**

```bash
# Start PostgreSQL container
docker compose up -d db

# Wait for PostgreSQL to be ready
docker compose exec db pg_isready -U beer_user -d beer_game

# Import converted SQL dump
docker compose exec -T db psql -U beer_user -d beer_game < backups/beer_game_postgres_converted.sql

# Check for errors
docker compose logs db | grep ERROR
```

**Method 2: Use SQLAlchemy to Create Schema, Then Import Data**

```bash
# Start PostgreSQL
docker compose up -d db

# Run init_db.py to create tables via SQLAlchemy
docker compose exec backend python -m app.db.init_db

# Verify tables created
docker compose exec db psql -U beer_user -d beer_game -c "\dt"

# Export data only from MariaDB (CSV format)
docker compose exec db mysql -u beer_user -p beer_game -e "
SELECT * FROM users INTO OUTFILE '/tmp/users.csv'
FIELDS TERMINATED BY ',' ENCLOSED BY '\"'
LINES TERMINATED BY '\n';
"

# Import CSV into PostgreSQL
docker compose exec db psql -U beer_user -d beer_game -c "
COPY users FROM '/tmp/users.csv' DELIMITER ',' CSV HEADER;
"

# Repeat for all 97 tables (or use script to automate)
```

### 5.4 Data Validation

**Step 1: Row Count Verification**

```bash
# Create validation script
cat > scripts/validate_migration.sh << 'EOF'
#!/bin/bash

echo "Validating MariaDB -> PostgreSQL Migration"
echo "==========================================="

# Tables to check
TABLES=(
  "users"
  "groups"
  "games"
  "players"
  "rounds"
  "player_rounds"
  "supply_chain_configs"
  "nodes"
  "lanes"
  "items"
  "agent_configs"
  "tenants"
  "sso_providers"
  "permissions"
  "roles"
  "audit_logs"
  "push_tokens"
  "notification_preferences"
  "notification_logs"
)

for table in "${TABLES[@]}"; do
  echo -n "Checking $table... "

  # MariaDB count
  maria_count=$(docker compose exec db mysql -u beer_user -p -N -e "SELECT COUNT(*) FROM beer_game.$table" 2>/dev/null)

  # PostgreSQL count
  pg_count=$(docker compose exec db psql -U beer_user -d beer_game -tAc "SELECT COUNT(*) FROM $table" 2>/dev/null)

  if [ "$maria_count" -eq "$pg_count" ]; then
    echo "✓ OK (MariaDB: $maria_count, PostgreSQL: $pg_count)"
  else
    echo "✗ MISMATCH (MariaDB: $maria_count, PostgreSQL: $pg_count)"
  fi
done
EOF

chmod +x scripts/validate_migration.sh
./scripts/validate_migration.sh
```

**Step 2: Data Integrity Checks**

```bash
# Check foreign key relationships
docker compose exec db psql -U beer_user -d beer_game << 'EOF'
-- Orphaned players (players without games)
SELECT COUNT(*) FROM players WHERE game_id NOT IN (SELECT id FROM games);

-- Orphaned rounds (rounds without games)
SELECT COUNT(*) FROM rounds WHERE game_id NOT IN (SELECT id FROM games);

-- Orphaned player_rounds (player_rounds without players)
SELECT COUNT(*) FROM player_rounds WHERE player_id NOT IN (SELECT id FROM players);

-- Users without groups
SELECT COUNT(*) FROM users WHERE group_id NOT IN (SELECT id FROM groups);
EOF
```

**Step 3: Critical Data Validation**

```bash
# Check system admin user exists
docker compose exec db psql -U beer_user -d beer_game -c "
SELECT id, email, role FROM users WHERE email='systemadmin@autonomy.ai';
"

# Check default supply chain configs exist
docker compose exec db psql -U beer_user -d beer_game -c "
SELECT id, name FROM supply_chain_configs WHERE name IN ('Default TBG', 'Three FG TBG', 'Variable TBG');
"

# Check game history preservation
docker compose exec db psql -U beer_user -d beer_game -c "
SELECT COUNT(*) AS total_games,
       COUNT(DISTINCT id) AS unique_games,
       MIN(created_at) AS oldest_game,
       MAX(created_at) AS newest_game
FROM games;
"
```

---

## 6. Testing Plan

### 6.1 Unit Tests

```bash
# Run backend unit tests
docker compose exec backend pytest tests/ -v

# Run specific test suites
docker compose exec backend pytest tests/test_db.py -v
docker compose exec backend pytest tests/test_models.py -v
docker compose exec backend pytest tests/test_agents.py -v
```

### 6.2 Integration Tests

**Test 1: Database Connection**
```bash
# Test sync connection
docker compose exec backend python -c "
from app.core.db_urls import get_database_url
from sqlalchemy import create_engine, text
url = get_database_url(sync=True)
print(f'URL: {url}')
engine = create_engine(url)
with engine.connect() as conn:
    result = conn.execute(text('SELECT version();'))
    print(f'PostgreSQL version: {result.scalar()}')
"

# Test async connection
docker compose exec backend python -c "
import asyncio
from app.core.db_urls import get_async_database_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def test():
    url = get_async_database_url()
    print(f'Async URL: {url}')
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        result = await conn.execute(text('SELECT version();'))
        print(f'PostgreSQL version: {result.scalar()}')
    await engine.dispose()

asyncio.run(test())
"
```

**Test 2: API Health Check**
```bash
# Start all services with PostgreSQL
docker compose up -d

# Wait for backend to be ready
sleep 15

# Test health endpoint
curl http://localhost:8000/health
# Expected: {"status":"healthy","database":"connected","timestamp":"..."}

# Test API docs
curl http://localhost:8000/docs
# Should return HTML
```

**Test 3: Authentication Flow**
```bash
# Test login
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "systemadmin@autonomy.ai",
    "password": "Autonomy@2026"
  }' | jq -r '.access_token')

echo "Token: $TOKEN"

# Test authenticated endpoint
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/users/me
```

**Test 4: Game Creation and Gameplay**
```bash
# Login
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"systemadmin@autonomy.ai","password":"Autonomy@2026"}' \
  | jq -r '.access_token')

# Create game
GAME_ID=$(curl -s -X POST http://localhost:8000/api/v1/mixed-games/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "PostgreSQL Migration Test Game",
    "config_name": "Default TBG",
    "max_rounds": 24,
    "players": [
      {"node_name": "Retailer", "strategy": "naive"},
      {"node_name": "Wholesaler", "strategy": "conservative"},
      {"node_name": "Distributor", "strategy": "ml_forecast"},
      {"node_name": "Factory", "strategy": "llm"}
    ]
  }' | jq -r '.id')

echo "Game ID: $GAME_ID"

# Start game
curl -s -X POST http://localhost:8000/api/v1/mixed-games/$GAME_ID/start \
  -H "Authorization: Bearer $TOKEN"

# Play 5 rounds
for i in {1..5}; do
  echo "Playing round $i..."
  curl -s -X POST http://localhost:8000/api/v1/mixed-games/$GAME_ID/play-round \
    -H "Authorization: Bearer $TOKEN" | jq '.round_number'
  sleep 2
done

# Get game state
curl -s http://localhost:8000/api/v1/mixed-games/$GAME_ID/state \
  -H "Authorization: Bearer $TOKEN" | jq '{round: .current_round, status: .status}'
```

**Test 5: GNN Training**
```bash
# Test GNN training endpoint
curl -s -X POST http://localhost:8000/api/v1/models/train \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "config_name": "Default TBG",
    "architecture": "temporal",
    "epochs": 2,
    "device": "cpu"
  }' | jq

# Check model status
curl -s http://localhost:8000/api/v1/model/status \
  -H "Authorization: Bearer $TOKEN" | jq
```

### 6.3 Performance Testing

**Test 1: Connection Pool Performance**
```bash
# Run concurrent requests
ab -n 1000 -c 10 -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/supply-chain-configs/

# Expected: No connection errors, < 100ms avg response time
```

**Test 2: Large Query Performance**
```bash
# Benchmark game history query
time curl -s http://localhost:8000/api/v1/agent-games/history?limit=100 \
  -H "Authorization: Bearer $TOKEN" | jq length

# Compare with MariaDB baseline (if available)
```

**Test 3: Database Query Analysis**
```bash
# Enable query logging in PostgreSQL
docker compose exec db psql -U beer_user -d beer_game << EOF
ALTER SYSTEM SET log_statement = 'all';
SELECT pg_reload_conf();
EOF

# Run typical workload
# ... (create games, play rounds, etc.)

# Analyze slow queries
docker compose exec db psql -U beer_user -d beer_game << EOF
SELECT query, calls, total_time, mean_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 20;
EOF
```

### 6.4 Stress Testing

```bash
# Create 100 concurrent games
for i in {1..100}; do
  curl -s -X POST http://localhost:8000/api/v1/agent-games/ \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "name": "Stress Test Game '$i'",
      "config_name": "Default TBG",
      "max_rounds": 24
    }' &
done
wait

# Check database health
docker compose exec db psql -U beer_user -d beer_game -c "
SELECT COUNT(*) FROM games;
SELECT COUNT(*) FROM pg_stat_activity;
"
```

---

## 7. Rollback Plan

### 7.1 Quick Rollback (< 5 minutes)

**Scenario**: Critical issue found immediately after migration

```bash
# 1. Stop PostgreSQL services
docker compose down

# 2. Restore MariaDB configuration
git checkout mariadb-baseline-$(date +%Y%m%d)

# 3. Start MariaDB services
docker compose up -d

# 4. Verify MariaDB data intact
docker compose exec db mysql -u root -p -e "USE beer_game; SELECT COUNT(*) FROM games;"

# 5. Restart backend
docker compose restart backend

# 6. Test health
curl http://localhost:8000/health
```

### 7.2 Full Rollback (30 minutes - 1 hour)

**Scenario**: Issues found after significant PostgreSQL usage

```bash
# 1. Stop all services
docker compose down

# 2. Backup PostgreSQL data (if needed for analysis)
docker compose up -d db
docker compose exec db pg_dump -U beer_user beer_game > backups/postgres_failed_migration.sql
docker compose down

# 3. Restore MariaDB code
git checkout mariadb-baseline-$(date +%Y%m%d)

# 4. Restore MariaDB data from backup
docker compose up -d db
sleep 10

docker compose exec -T db mysql -u root -p < backups/mariadb_$(date +%Y%m%d)/beer_game_full_backup.sql

# 5. Verify data restored
docker compose exec db mysql -u root -p -e "
USE beer_game;
SELECT COUNT(*) AS users FROM users;
SELECT COUNT(*) AS games FROM games;
SELECT COUNT(*) AS rounds FROM rounds;
"

# 6. Rebuild and restart backend
docker compose build backend
docker compose up -d

# 7. Run smoke tests
curl http://localhost:8000/health
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"systemadmin@autonomy.ai","password":"Autonomy@2026"}' \
  | jq -r '.access_token')
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/users/me

# 8. Update stakeholders
echo "Rollback complete. MariaDB restored from backup."
```

### 7.3 Partial Rollback (Data Loss Recovery)

**Scenario**: Need to recover specific data from MariaDB backup

```bash
# 1. Export specific table from MariaDB backup
docker compose -f docker-compose-mariadb.yml up -d db_mariadb
docker compose exec db_mariadb mysql -u root -p beer_game -e "SELECT * FROM games WHERE created_at > '2026-01-15'" > lost_games.sql

# 2. Convert to PostgreSQL format
python scripts/convert_mariadb_to_postgres.py lost_games.sql lost_games_pg.sql

# 3. Import into PostgreSQL
docker compose exec -T db psql -U beer_user -d beer_game < lost_games_pg.sql

# 4. Verify recovery
docker compose exec db psql -U beer_user -d beer_game -c "SELECT COUNT(*) FROM games WHERE created_at > '2026-01-15';"
```

---

## 8. Post-Migration Validation

### 8.1 Comprehensive Validation Checklist

- [ ] **Database Connection**: Backend connects to PostgreSQL successfully
- [ ] **Table Count**: All 97 tables exist in PostgreSQL
- [ ] **Row Counts**: All tables have correct row counts (match MariaDB)
- [ ] **Foreign Keys**: All foreign key relationships intact
- [ ] **Indexes**: All indexes created correctly
- [ ] **Sequences**: All SERIAL sequences start at correct values
- [ ] **Default Values**: All column defaults preserved
- [ ] **NOT NULL Constraints**: All constraints preserved
- [ ] **UNIQUE Constraints**: All unique constraints working
- [ ] **ENUM Values**: All ENUM types have correct values
- [ ] **JSON Columns**: JSON data readable and queryable
- [ ] **TEXT Columns**: Large text fields preserved
- [ ] **TIMESTAMP Columns**: Timestamps with correct timezone handling
- [ ] **Authentication**: Login/logout working
- [ ] **Authorization**: RBAC permissions enforced
- [ ] **API Endpoints**: All 159 endpoints responding correctly
- [ ] **Game Creation**: Can create new games
- [ ] **Gameplay**: Can play rounds and complete games
- [ ] **Agent Strategies**: All 7 agent types working
- [ ] **GNN Training**: Can train temporal GNN
- [ ] **GNN Inference**: ML agents making predictions
- [ ] **WebSocket**: Real-time updates broadcasting
- [ ] **File Uploads**: Config imports working
- [ ] **Data Exports**: Game history exports working
- [ ] **Audit Logs**: Audit logging capturing events
- [ ] **Push Notifications**: Notification system operational (if testing mobile)
- [ ] **Performance**: Response times comparable to MariaDB
- [ ] **Connection Pooling**: No connection exhaustion under load
- [ ] **Error Handling**: Appropriate errors for invalid requests

### 8.2 Automated Validation Script

Create `scripts/validate_postgres_migration.sh`:

```bash
#!/bin/bash

echo "======================================"
echo "PostgreSQL Migration Validation Suite"
echo "======================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

pass_count=0
fail_count=0

test_pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((pass_count++))
}

test_fail() {
    echo -e "${RED}✗${NC} $1"
    ((fail_count++))
}

# Test 1: Database connection
echo "Test 1: Database Connection"
if docker compose exec db pg_isready -U beer_user -d beer_game > /dev/null 2>&1; then
    test_pass "PostgreSQL is ready"
else
    test_fail "PostgreSQL not responding"
fi
echo ""

# Test 2: Table count
echo "Test 2: Table Count"
table_count=$(docker compose exec db psql -U beer_user -d beer_game -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';")
if [ "$table_count" -eq 97 ]; then
    test_pass "All 97 tables exist"
else
    test_fail "Expected 97 tables, found $table_count"
fi
echo ""

# Test 3: Critical tables exist
echo "Test 3: Critical Tables"
for table in users groups games players rounds player_rounds supply_chain_configs nodes lanes items agent_configs; do
    if docker compose exec db psql -U beer_user -d beer_game -tAc "SELECT 1 FROM $table LIMIT 1" > /dev/null 2>&1; then
        test_pass "Table '$table' exists and accessible"
    else
        test_fail "Table '$table' missing or inaccessible"
    fi
done
echo ""

# Test 4: Backend health
echo "Test 4: Backend Health"
if curl -sf http://localhost:8000/health | grep -q "healthy"; then
    test_pass "Backend health check passed"
else
    test_fail "Backend health check failed"
fi
echo ""

# Test 5: Authentication
echo "Test 5: Authentication"
TOKEN=$(curl -sf -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"systemadmin@autonomy.ai","password":"Autonomy@2026"}' \
  | jq -r '.access_token')

if [ -n "$TOKEN" ] && [ "$TOKEN" != "null" ]; then
    test_pass "Authentication successful"
else
    test_fail "Authentication failed"
fi
echo ""

# Test 6: User data
echo "Test 6: User Data"
user_count=$(docker compose exec db psql -U beer_user -d beer_game -tAc "SELECT COUNT(*) FROM users;")
if [ "$user_count" -gt 0 ]; then
    test_pass "Users table has $user_count records"
else
    test_fail "Users table is empty"
fi
echo ""

# Test 7: Supply chain configs
echo "Test 7: Supply Chain Configs"
config_count=$(docker compose exec db psql -U beer_user -d beer_game -tAc "SELECT COUNT(*) FROM supply_chain_configs WHERE name IN ('Default TBG', 'Three FG TBG', 'Variable TBG');")
if [ "$config_count" -eq 3 ]; then
    test_pass "All default configs exist"
else
    test_fail "Expected 3 default configs, found $config_count"
fi
echo ""

# Test 8: Foreign keys
echo "Test 8: Foreign Key Integrity"
orphans=$(docker compose exec db psql -U beer_user -d beer_game -tAc "SELECT COUNT(*) FROM players WHERE game_id NOT IN (SELECT id FROM games);")
if [ "$orphans" -eq 0 ]; then
    test_pass "No orphaned players"
else
    test_fail "Found $orphans orphaned players"
fi
echo ""

# Test 9: Indexes
echo "Test 9: Indexes"
index_count=$(docker compose exec db psql -U beer_user -d beer_game -tAc "SELECT COUNT(*) FROM pg_indexes WHERE schemaname='public';")
if [ "$index_count" -gt 50 ]; then
    test_pass "Indexes created ($index_count indexes)"
else
    test_fail "Insufficient indexes ($index_count found)"
fi
echo ""

# Test 10: API endpoints
echo "Test 10: API Endpoints"
if curl -sf -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/supply-chain-configs/ | jq -e 'length > 0' > /dev/null; then
    test_pass "API endpoints responding"
else
    test_fail "API endpoints not responding"
fi
echo ""

# Summary
echo "======================================"
echo "Summary"
echo "======================================"
echo -e "Passed: ${GREEN}$pass_count${NC}"
echo -e "Failed: ${RED}$fail_count${NC}"
echo ""

if [ $fail_count -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed! Migration successful.${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed. Review issues above.${NC}"
    exit 1
fi
```

Run validation:
```bash
chmod +x scripts/validate_postgres_migration.sh
./scripts/validate_postgres_migration.sh
```

---

## 9. Performance Tuning

### 9.1 PostgreSQL Configuration Tuning

**File**: `postgresql.conf`

**For Production** (adjust based on available resources):

```conf
# Memory Settings (for 8GB RAM server)
shared_buffers = 2GB                    # 25% of system RAM
effective_cache_size = 6GB              # 75% of system RAM
work_mem = 16MB                         # Per operation memory
maintenance_work_mem = 512MB            # For VACUUM, CREATE INDEX

# Write Ahead Log (WAL)
wal_buffers = 16MB
min_wal_size = 1GB
max_wal_size = 4GB
checkpoint_completion_target = 0.9
wal_compression = on

# Query Planning
default_statistics_target = 100
random_page_cost = 1.1                  # For SSD (1.1-1.5), for HDD (4.0)
effective_io_concurrency = 200          # For SSD (100-500)

# Connection Settings
max_connections = 200
superuser_reserved_connections = 3
idle_in_transaction_session_timeout = 600000  # 10 minutes

# Parallel Query
max_worker_processes = 8
max_parallel_workers_per_gather = 4
max_parallel_workers = 8

# Autovacuum (critical for PostgreSQL performance)
autovacuum = on
autovacuum_max_workers = 4
autovacuum_naptime = 30s
autovacuum_vacuum_threshold = 50
autovacuum_analyze_threshold = 50
autovacuum_vacuum_scale_factor = 0.05   # More aggressive than default (0.2)
autovacuum_analyze_scale_factor = 0.05
```

### 9.2 Index Optimization

**Verify Critical Indexes**:

```sql
-- Check indexes on frequently queried columns
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;

-- Find missing indexes (tables with sequential scans)
SELECT
    schemaname,
    tablename,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch,
    CASE WHEN seq_scan > 0 THEN
        ROUND((100.0 * idx_scan) / (seq_scan + idx_scan), 2)
    ELSE 0 END AS index_usage_percent
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY seq_tup_read DESC
LIMIT 20;
```

**Add Missing Indexes** (if needed):

```sql
-- Example: Add indexes identified during performance testing
CREATE INDEX CONCURRENTLY idx_rounds_game_id_round_number
ON rounds (game_id, round_number);

CREATE INDEX CONCURRENTLY idx_player_rounds_player_id_round_id
ON player_rounds (player_id, round_id);

CREATE INDEX CONCURRENTLY idx_audit_logs_created_at
ON audit_logs (created_at DESC);

-- Composite indexes for common JOIN patterns
CREATE INDEX CONCURRENTLY idx_players_game_node
ON players (game_id, node_id);
```

### 9.3 Query Optimization

**Enable Query Statistics**:

```sql
-- Install pg_stat_statements extension
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- View slowest queries
SELECT
    query,
    calls,
    total_time,
    mean_time,
    max_time,
    stddev_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 20;
```

**Analyze Query Plans**:

```sql
-- Example: Analyze game history query
EXPLAIN ANALYZE
SELECT g.id, g.name, g.current_round, g.status,
       COUNT(DISTINCT p.id) AS player_count,
       COUNT(DISTINCT r.id) AS round_count
FROM games g
LEFT JOIN players p ON g.id = p.game_id
LEFT JOIN rounds r ON g.id = r.game_id
WHERE g.created_at > NOW() - INTERVAL '30 days'
GROUP BY g.id, g.name, g.current_round, g.status
ORDER BY g.created_at DESC
LIMIT 50;
```

### 9.4 Connection Pooling Tuning

**File**: `backend/app/db/session.py`

**Optimize SQLAlchemy Pool Settings**:

```python
engine = create_engine(
    database_url,
    echo=False,
    pool_pre_ping=True,        # Verify connections before using
    pool_recycle=300,           # Recycle connections after 5 minutes
    pool_size=20,               # Increase from 5 to 20 (adjust based on max_connections)
    max_overflow=40,            # Increase from 10 to 40
    pool_timeout=30,            # Wait up to 30s for connection
    connect_args={
        "connect_timeout": 10,  # PostgreSQL connection timeout
        "options": "-c timezone=utc",
    }
)
```

### 9.5 Monitoring Setup

**Install pgAdmin** (optional):

```yaml
# Add to docker-compose.yml
  pgadmin:
    image: dpage/pgadmin4:latest
    container_name: beer_game_pgadmin
    restart: unless-stopped
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@autonomy.ai
      PGADMIN_DEFAULT_PASSWORD: admin
    ports:
      - "5050:80"
    networks:
      - beer_game_network
    depends_on:
      - db
```

**PostgreSQL Monitoring Queries**:

```sql
-- Active connections
SELECT COUNT(*) AS connections,
       state,
       wait_event_type
FROM pg_stat_activity
WHERE datname = 'beer_game'
GROUP BY state, wait_event_type;

-- Database size
SELECT pg_size_pretty(pg_database_size('beer_game'));

-- Table sizes
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size,
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS table_size,
    pg_size_pretty(pg_indexes_size(schemaname||'.'||tablename)) AS indexes_size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 20;

-- Cache hit ratio (should be > 99%)
SELECT
    SUM(heap_blks_read) AS heap_read,
    SUM(heap_blks_hit) AS heap_hit,
    ROUND(SUM(heap_blks_hit) / (SUM(heap_blks_hit) + SUM(heap_blks_read)), 4) * 100 AS cache_hit_ratio
FROM pg_statio_user_tables;
```

---

## 10. Known Issues and Workarounds

### 10.1 Alembic Migration Issues

**Issue**: Some Alembic migrations may have MariaDB-specific SQL

**Workaround**:
```bash
# Option 1: Skip Alembic, use SQLAlchemy metadata
docker compose exec backend python -m app.db.init_db
# This creates all tables from SQLAlchemy models

# Option 2: Review and fix migration files manually
# Edit files in backend/alembic/versions/ to remove MariaDB syntax

# Option 3: Reset Alembic history
rm -rf backend/alembic/versions/*
docker compose exec backend alembic revision --autogenerate -m "Initial PostgreSQL schema"
docker compose exec backend alembic upgrade head
```

### 10.2 ENUM Type Differences

**Issue**: PostgreSQL creates native ENUM types, MariaDB uses string constraints

**Symptoms**:
```
ERROR: column "status" is of type gamestatus but expression is of type character varying
```

**Workaround**:
```sql
-- If migration fails, manually create ENUM types first
CREATE TYPE gamestatus AS ENUM ('pending', 'active', 'completed', 'cancelled');
CREATE TYPE playerrole AS ENUM ('RETAILER', 'WHOLESALER', 'DISTRIBUTOR', 'FACTORY');
-- ... etc for all ENUMs

-- Then run migrations
```

**Or update models to use String instead of Enum**:
```python
# Before
status = Column(Enum(GameStatus), default=GameStatus.PENDING)

# After (temporary workaround)
status = Column(String(20), default="pending")
```

### 10.3 AUTO_INCREMENT vs SERIAL

**Issue**: MariaDB AUTO_INCREMENT sequences don't transfer to PostgreSQL

**Symptoms**:
```
ERROR: duplicate key value violates unique constraint "users_pkey"
DETAIL: Key (id)=(1) already exists.
```

**Workaround**:
```sql
-- Reset all sequences to correct values after data import
SELECT 'SELECT SETVAL(' ||
       quote_literal(quote_ident(PGT.schemaname) || '.' || quote_ident(S.relname)) ||
       ', COALESCE(MAX(' ||quote_ident(C.attname)|| '), 1) ) FROM ' ||
       quote_ident(PGT.schemaname)|| '.'||quote_ident(T.relname)|| ';'
FROM pg_class AS S,
     pg_depend AS D,
     pg_class AS T,
     pg_attribute AS C,
     pg_tables AS PGT
WHERE S.relkind = 'S'
    AND S.oid = D.objid
    AND D.refobjid = T.oid
    AND D.refobjid = C.attrelid
    AND D.refobjsubid = C.attnum
    AND T.relname = PGT.tablename
    AND PGT.schemaname = 'public'
ORDER BY S.relname;

-- Run the output of the above query
```

Or use automated script:
```bash
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

### 10.4 Timezone Handling

**Issue**: PostgreSQL handles timezones differently than MariaDB

**MariaDB**: Stores DATETIME without timezone info
**PostgreSQL**: Recommends TIMESTAMPTZ (timestamp with timezone)

**Best Practice**:
```python
# In models, use timezone-aware datetime
from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import TIMESTAMP

# For PostgreSQL
created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)

# Or use SQLAlchemy's generic DateTime with timezone=True
created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
```

**Conversion**:
```sql
-- Convert existing TIMESTAMP to TIMESTAMPTZ (if needed)
ALTER TABLE games ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC';
```

### 10.5 JSON Column Differences

**Issue**: MariaDB JSON vs PostgreSQL JSONB

**PostgreSQL Advantage**: JSONB is binary format, faster indexing and queries

**Update Models**:
```python
from sqlalchemy.dialects.postgresql import JSONB

# Before
config = Column(JSON, nullable=True)

# After (PostgreSQL-specific optimization)
config = Column(JSONB, nullable=True)
```

**Create GIN Indexes for JSONB**:
```sql
CREATE INDEX CONCURRENTLY idx_supply_chain_configs_config_gin
ON supply_chain_configs USING GIN (config);

CREATE INDEX CONCURRENTLY idx_agent_configs_parameters_gin
ON agent_configs USING GIN (parameters);
```

### 10.6 Full Text Search

**Issue**: MariaDB uses FULLTEXT indexes, PostgreSQL uses tsvector

**If you have full-text search** (currently not in your schema):

```sql
-- PostgreSQL full-text search setup
ALTER TABLE games ADD COLUMN search_vector tsvector;

CREATE INDEX idx_games_search_vector ON games USING GIN(search_vector);

-- Update trigger to maintain search_vector
CREATE FUNCTION games_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', COALESCE(NEW.name, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.description, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER games_search_vector_trigger
BEFORE INSERT OR UPDATE ON games
FOR EACH ROW EXECUTE FUNCTION games_search_vector_update();
```

---

## 11. Implementation Checklist

### Day 1: Preparation ✅

- [ ] **Backup** all data from MariaDB
- [ ] **Create git branch** `postgres-migration`
- [ ] **Update** `requirements.txt` (remove MySQL deps, add PostgreSQL)
- [ ] **Update** Dockerfiles (CPU, GPU, prod)
- [ ] **Update** `db_urls.py` (add PostgreSQL support)
- [ ] **Update** `session.py` (verify connection pooling)
- [ ] **Create** `init_db_postgres.sql`
- [ ] **Create** `postgresql.conf`
- [ ] **Update** `docker-compose.yml` (db service)
- [ ] **Update** `docker-compose.db.yml` (db service)
- [ ] **Update** `docker-compose.prod.yml` (db service)
- [ ] **Update** `.env` (PostgreSQL variables)
- [ ] **Update** `alembic.ini` (PostgreSQL URL)
- [ ] **Update** `alembic/env.py` (database type detection)
- [ ] **Commit** all changes

### Day 2: Migration ✅

- [ ] **Build** new Docker images (`docker compose build`)
- [ ] **Start** PostgreSQL (`docker compose up -d db`)
- [ ] **Wait** for PostgreSQL ready (`pg_isready`)
- [ ] **Run** init_db.py to create schema
- [ ] **Verify** 97 tables created
- [ ] **Export** data from MariaDB (mysqldump)
- [ ] **Convert** SQL dump to PostgreSQL format
- [ ] **Import** data into PostgreSQL
- [ ] **Reset** sequences to correct values
- [ ] **Validate** row counts match
- [ ] **Validate** foreign key integrity
- [ ] **Commit** migration scripts

### Day 3: Testing ✅

- [ ] **Start** all services with PostgreSQL
- [ ] **Run** backend health check
- [ ] **Test** authentication (login/logout)
- [ ] **Test** user management
- [ ] **Test** game creation
- [ ] **Test** gameplay (play 10 rounds)
- [ ] **Test** all 7 agent strategies
- [ ] **Test** GNN training
- [ ] **Test** GNN inference (ml_forecast agent)
- [ ] **Test** LLM agent (if OpenAI configured)
- [ ] **Test** WebSocket real-time updates
- [ ] **Test** data export/import
- [ ] **Test** API endpoints (all 159)
- [ ] **Run** validation script
- [ ] **Run** performance benchmarks
- [ ] **Document** any issues found
- [ ] **Fix** critical issues
- [ ] **Retest** after fixes

### Day 4: Production Deployment ✅

- [ ] **Schedule** maintenance window
- [ ] **Notify** stakeholders
- [ ] **Final** MariaDB backup
- [ ] **Deploy** PostgreSQL configuration to production
- [ ] **Migrate** production data
- [ ] **Start** services
- [ ] **Run** smoke tests
- [ ] **Monitor** logs for errors
- [ ] **Monitor** performance metrics
- [ ] **Verify** all critical features working
- [ ] **Update** documentation
- [ ] **Communicate** completion
- [ ] **Monitor** for 24 hours
- [ ] **Celebrate** successful migration! 🎉

---

## 12. Quick Reference Commands

### Database Management

```bash
# PostgreSQL shell
docker compose exec db psql -U beer_user -d beer_game

# List tables
docker compose exec db psql -U beer_user -d beer_game -c "\dt"

# Table details
docker compose exec db psql -U beer_user -d beer_game -c "\d+ users"

# Database size
docker compose exec db psql -U beer_user -d beer_game -c "SELECT pg_size_pretty(pg_database_size('beer_game'));"

# Row count for all tables
docker compose exec db psql -U beer_user -d beer_game -c "
SELECT schemaname, tablename, n_live_tup
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC;
"

# Active connections
docker compose exec db psql -U beer_user -d beer_game -c "
SELECT COUNT(*), state FROM pg_stat_activity
WHERE datname='beer_game'
GROUP BY state;
"
```

### Docker Management

```bash
# Start PostgreSQL only
docker compose up -d db

# Rebuild backend with new dependencies
docker compose build backend

# View logs
docker compose logs db -f
docker compose logs backend -f

# Restart services
docker compose restart backend
docker compose restart db

# Stop all services
docker compose down

# Remove volumes (WARNING: deletes data)
docker compose down -v
```

### Backup & Restore

```bash
# Backup PostgreSQL
docker compose exec db pg_dump -U beer_user beer_game > backups/beer_game_$(date +%Y%m%d).sql

# Restore PostgreSQL
docker compose exec -T db psql -U beer_user -d beer_game < backups/beer_game_20260116.sql

# Export specific table
docker compose exec db pg_dump -U beer_user -t games beer_game > games_backup.sql

# Import specific table
docker compose exec -T db psql -U beer_user -d beer_game < games_backup.sql
```

### Performance Monitoring

```bash
# Cache hit ratio
docker compose exec db psql -U beer_user -d beer_game -c "
SELECT
  SUM(heap_blks_hit) / (SUM(heap_blks_hit) + SUM(heap_blks_read)) * 100 AS cache_hit_ratio
FROM pg_statio_user_tables;
"

# Slow queries (requires pg_stat_statements)
docker compose exec db psql -U beer_user -d beer_game -c "
SELECT query, calls, mean_time, max_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;
"

# Table sizes
docker compose exec db psql -U beer_user -d beer_game -c "
SELECT tablename,
       pg_size_pretty(pg_total_relation_size('public.'||tablename)) AS total_size
FROM pg_tables
WHERE schemaname='public'
ORDER BY pg_total_relation_size('public.'||tablename) DESC
LIMIT 10;
"
```

---

## 13. Summary

### Migration Overview

**Scope**: Complete database migration from MariaDB 10.11 to PostgreSQL 16

**Files to Change**: ~45 files
- 12 critical files (code and config)
- 3 Docker Compose files
- 3 Dockerfiles
- 17+ Alembic migration files (review only)
- Multiple documentation and configuration files

**Database**: 97 tables, all data preserved

**Estimated Effort**:
- Day 1 (Preparation): 4-6 hours
- Day 2 (Migration): 4-6 hours
- Day 3 (Testing): 6-8 hours
- Day 4 (Production): 2-4 hours
- **Total**: 16-24 hours

**Risk Level**: Medium
- Substantial code changes
- Data migration complexity
- Testing requirements
- Rollback plan available

### Why PostgreSQL?

**Advantages over MariaDB**:
1. **Better JSON Support**: JSONB with indexing (GIN indexes)
2. **Advanced Features**: Window functions, CTEs, full-text search
3. **Scalability**: Better handling of concurrent writes
4. **Extensibility**: Rich extension ecosystem (PostGIS, pg_trgm, etc.)
5. **Community**: Larger developer community
6. **Cloud Support**: Better integration with cloud providers
7. **Standards Compliance**: More SQL standard compliant

### Next Steps

1. **Review this plan** thoroughly
2. **Schedule** migration timeline
3. **Backup** all MariaDB data
4. **Execute** Phase 1 (Preparation)
5. **Test** in development environment
6. **Execute** Phases 2-3 (Migration and Testing)
7. **Schedule** production deployment
8. **Execute** Phase 4 (Production)
9. **Monitor** and tune performance

### Support Resources

- **PostgreSQL Documentation**: https://www.postgresql.org/docs/16/
- **SQLAlchemy PostgreSQL**: https://docs.sqlalchemy.org/en/20/dialects/postgresql.html
- **Alembic Migrations**: https://alembic.sqlalchemy.org/
- **Docker PostgreSQL**: https://hub.docker.com/_/postgres
- **pgloader Tool**: https://pgloader.io/

---

## Questions or Issues?

If you encounter issues during migration:

1. Check logs: `docker compose logs db backend`
2. Review [Known Issues](#10-known-issues-and-workarounds)
3. Run validation script: `./scripts/validate_postgres_migration.sh`
4. Test rollback procedure in dev environment
5. Document issues for resolution

**Good luck with your migration!** 🚀

---

**Document Version**: 1.0
**Last Updated**: 2026-01-16
**Status**: Ready for Implementation
