#!/bin/bash
#
# Rollback Script
# Phase 6 Sprint 5: Production Deployment & Testing
#
# Rollback to a previous deployment version
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
ENVIRONMENT="${1}"
BACKUP_VERSION="${2}"

# Directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${PROJECT_ROOT}/backups"

echo -e "${BLUE}=================================="
echo "Beer Game Rollback Script"
echo "==================================${NC}"
echo ""

# Validate arguments
if [ -z "$ENVIRONMENT" ] || [ -z "$BACKUP_VERSION" ]; then
    echo -e "${RED}Usage: $0 <environment> <backup_version>${NC}"
    echo ""
    echo "Available backups:"
    ls -1 "$BACKUP_DIR" 2>/dev/null || echo "  No backups found"
    exit 1
fi

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(staging|production)$ ]]; then
    echo -e "${RED}Error: Invalid environment. Must be 'staging' or 'production'${NC}"
    exit 1
fi

# Validate backup exists
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_VERSION}"
if [ ! -d "$BACKUP_PATH" ]; then
    echo -e "${RED}Error: Backup not found: ${BACKUP_PATH}${NC}"
    exit 1
fi

echo "Environment: ${ENVIRONMENT}"
echo "Backup Version: ${BACKUP_VERSION}"
echo ""

# Confirm rollback
echo -e "${YELLOW}⚠️  WARNING: This will rollback to a previous version${NC}"
read -p "Are you sure you want to continue? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Rollback cancelled"
    exit 0
fi

# Function to log with timestamp
log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Rollback process
log "${BLUE}Starting rollback process...${NC}"

# Step 1: Stop current containers
log "Stopping current containers..."
cd "$PROJECT_ROOT"
docker compose -f docker-compose.yml -f docker-compose.prod.yml down

# Step 2: Restore docker-compose files
log "Restoring docker-compose configuration..."
cp "${BACKUP_PATH}/docker-compose.yml" "${PROJECT_ROOT}/" 2>/dev/null || true
cp "${BACKUP_PATH}/docker-compose.prod.yml" "${PROJECT_ROOT}/" 2>/dev/null || true

# Step 3: Load backup images
log "Loading backup images..."
if [ -f "${BACKUP_PATH}/backend.tar" ]; then
    docker load -i "${BACKUP_PATH}/backend.tar"
    log "${GREEN}✓ Backend image loaded${NC}"
fi

if [ -f "${BACKUP_PATH}/frontend.tar" ]; then
    docker load -i "${BACKUP_PATH}/frontend.tar"
    log "${GREEN}✓ Frontend image loaded${NC}"
fi

# Step 4: Start database
log "Starting database..."
docker compose up -d db
sleep 15

# Step 5: Restore database
log "Restoring database..."
if [ -f "${BACKUP_PATH}/database.sql" ]; then
    # Load environment variables
    source "${PROJECT_ROOT}/.env"

    # Restore database
    docker compose exec -T db mysql -u root -p${MARIADB_ROOT_PASSWORD} autonomy \
        < "${BACKUP_PATH}/database.sql"

    log "${GREEN}✓ Database restored${NC}"
else
    log "${YELLOW}⚠️  No database backup found, skipping restore${NC}"
fi

# Step 6: Start all containers
log "Starting all containers..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Step 7: Wait for services to be ready
log "Waiting for services to be ready..."
sleep 30

# Step 8: Verify rollback
log "Verifying rollback..."

# Check backend health
HEALTH_URL="http://localhost:8000/api/v1/health/ready"
if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
    log "${GREEN}✓ Backend is healthy${NC}"
else
    log "${RED}✗ Backend health check failed${NC}"
    exit 1
fi

# Check database connectivity
if docker compose exec -T backend python -c "from app.db.session import SessionLocal; SessionLocal().execute('SELECT 1')" 2>/dev/null; then
    log "${GREEN}✓ Database connectivity verified${NC}"
else
    log "${RED}✗ Database connectivity check failed${NC}"
    exit 1
fi

# Success
log "${GREEN}✓✓✓ Rollback completed successfully ✓✓✓${NC}"
log ""
log "Rollback Details:"
log "  Environment: ${ENVIRONMENT}"
log "  Backup Version: ${BACKUP_VERSION}"
log "  Backup Path: ${BACKUP_PATH}"
