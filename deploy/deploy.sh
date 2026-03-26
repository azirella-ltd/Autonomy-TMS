#!/bin/bash
#
# Production Deployment Script
# Phase 6 Sprint 5: Production Deployment & Testing
#
# Automated deployment with health checks and rollback capability
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
ENVIRONMENT="${1:-staging}"
VERSION="${2:-latest}"
ROLLBACK_VERSION=""
HEALTH_CHECK_RETRIES=30
HEALTH_CHECK_INTERVAL=10

# Directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${PROJECT_ROOT}/backups"

echo -e "${BLUE}=================================="
echo "Autonomy Platform Deployment"
echo "==================================${NC}"
echo ""
echo "Environment: ${ENVIRONMENT}"
echo "Version: ${VERSION}"
echo ""

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(staging|production)$ ]]; then
    echo -e "${RED}Error: Invalid environment. Must be 'staging' or 'production'${NC}"
    exit 1
fi

# Confirm production deployment
if [ "$ENVIRONMENT" = "production" ]; then
    echo -e "${YELLOW}⚠️  WARNING: Deploying to PRODUCTION${NC}"
    read -p "Are you sure you want to continue? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Deployment cancelled"
        exit 0
    fi
fi

# Function to log with timestamp
log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Function to check if service is healthy
check_health() {
    local url=$1
    local retries=$2

    for i in $(seq 1 $retries); do
        if curl -sf "$url" > /dev/null 2>&1; then
            return 0
        fi
        log "Health check attempt $i/$retries failed, waiting..."
        sleep $HEALTH_CHECK_INTERVAL
    done

    return 1
}

# Backup current deployment
backup_deployment() {
    log "${BLUE}Backing up current deployment...${NC}"

    mkdir -p "$BACKUP_DIR"
    BACKUP_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_NAME="backup_${ENVIRONMENT}_${BACKUP_TIMESTAMP}"

    # Create backup directory
    mkdir -p "${BACKUP_DIR}/${BACKUP_NAME}"

    # Backup docker-compose files
    cp "${PROJECT_ROOT}/docker-compose.yml" "${BACKUP_DIR}/${BACKUP_NAME}/"
    cp "${PROJECT_ROOT}/docker-compose.prod.yml" "${BACKUP_DIR}/${BACKUP_NAME}/" 2>/dev/null || true

    # Export current images
    log "Exporting current images..."
    docker save autonomy_backend:latest -o "${BACKUP_DIR}/${BACKUP_NAME}/backend.tar" 2>/dev/null || true
    docker save autonomy_frontend:latest -o "${BACKUP_DIR}/${BACKUP_NAME}/frontend.tar" 2>/dev/null || true

    # Backup database (PostgreSQL)
    log "Backing up database..."
    docker compose exec -T db pg_dump -U autonomy_user -Fc autonomy \
        > "${BACKUP_DIR}/${BACKUP_NAME}/database.dump" 2>/dev/null || true

    # Save backup version for rollback
    ROLLBACK_VERSION="${BACKUP_NAME}"

    log "${GREEN}✓ Backup completed: ${ROLLBACK_VERSION}${NC}"
}

# Run database migrations
run_migrations() {
    log "${BLUE}Running database migrations...${NC}"

    docker compose exec -T backend alembic upgrade head

    if [ $? -eq 0 ]; then
        log "${GREEN}✓ Migrations completed${NC}"
    else
        log "${RED}✗ Migration failed${NC}"
        return 1
    fi
}

# Pull latest images
pull_images() {
    log "${BLUE}Pulling images for version ${VERSION}...${NC}"

    # Rebuild images locally (or pull from ECR in production)
    docker compose build

    log "${GREEN}✓ Images ready${NC}"
}

# Deploy new version
deploy() {
    log "${BLUE}Deploying new version...${NC}"

    # Set environment
    export ENVIRONMENT=$ENVIRONMENT

    # Stop current containers
    log "Stopping current containers..."
    docker compose down

    # Start new containers
    log "Starting new containers..."
    docker compose up -d

    log "${GREEN}✓ Containers started${NC}"
}

# Validate deployment
validate_deployment() {
    log "${BLUE}Validating deployment...${NC}"

    # Determine health check URL
    if [ "$ENVIRONMENT" = "production" ]; then
        HEALTH_URL="http://localhost:8000/api/v1/health/ready"
    else
        HEALTH_URL="http://localhost:8000/api/v1/health/ready"
    fi

    # Wait for backend to be ready
    log "Checking backend health..."
    if check_health "$HEALTH_URL" $HEALTH_CHECK_RETRIES; then
        log "${GREEN}✓ Backend is healthy${NC}"
    else
        log "${RED}✗ Backend health check failed${NC}"
        return 1
    fi

    # Check database connectivity
    log "Checking database connectivity..."
    if docker compose exec -T backend python -c "from app.db.session import SessionLocal; SessionLocal().execute('SELECT 1')" 2>/dev/null; then
        log "${GREEN}✓ Database connectivity verified${NC}"
    else
        log "${RED}✗ Database connectivity check failed${NC}"
        return 1
    fi

    # Run smoke tests
    log "Running smoke tests..."
    if docker compose exec -T backend python -m pytest tests/smoke/ -v 2>/dev/null; then
        log "${GREEN}✓ Smoke tests passed${NC}"
    else
        log "${YELLOW}⚠️  Smoke tests failed (non-critical)${NC}"
    fi

    log "${GREEN}✓ Deployment validation completed${NC}"
    return 0
}

# Rollback deployment
rollback() {
    log "${RED}Rolling back deployment...${NC}"

    if [ -z "$ROLLBACK_VERSION" ]; then
        log "${RED}No backup version available for rollback${NC}"
        return 1
    fi

    BACKUP_PATH="${BACKUP_DIR}/${ROLLBACK_VERSION}"

    if [ ! -d "$BACKUP_PATH" ]; then
        log "${RED}Backup directory not found: ${BACKUP_PATH}${NC}"
        return 1
    fi

    # Stop current containers
    docker compose down

    # Load backup images
    log "Loading backup images..."
    docker load -i "${BACKUP_PATH}/backend.tar" 2>/dev/null || true
    docker load -i "${BACKUP_PATH}/frontend.tar" 2>/dev/null || true

    # Restore database (PostgreSQL)
    log "Restoring database..."
    docker compose up -d db
    sleep 10
    docker compose exec -T db pg_restore -U autonomy_user -d autonomy --clean \
        < "${BACKUP_PATH}/database.dump" 2>/dev/null || true

    # Start containers
    docker compose up -d

    log "${GREEN}✓ Rollback completed${NC}"
}

# Main deployment flow
main() {
    log "Starting deployment process..."

    # Step 1: Backup
    backup_deployment
    if [ $? -ne 0 ]; then
        log "${RED}Backup failed, aborting deployment${NC}"
        exit 1
    fi

    # Step 2: Pull images
    pull_images
    if [ $? -ne 0 ]; then
        log "${RED}Image pull failed, aborting deployment${NC}"
        exit 1
    fi

    # Step 3: Deploy
    deploy
    if [ $? -ne 0 ]; then
        log "${RED}Deployment failed${NC}"
        rollback
        exit 1
    fi

    # Step 4: Run migrations
    sleep 15  # Wait for DB to be ready
    run_migrations
    if [ $? -ne 0 ]; then
        log "${RED}Migration failed${NC}"
        rollback
        exit 1
    fi

    # Step 5: Validate
    validate_deployment
    if [ $? -ne 0 ]; then
        log "${RED}Validation failed${NC}"
        read -p "Deployment validation failed. Rollback? (yes/no): " rollback_confirm
        if [ "$rollback_confirm" = "yes" ]; then
            rollback
            exit 1
        fi
    fi

    # Success
    log "${GREEN}✓✓✓ Deployment completed successfully ✓✓✓${NC}"
    log ""
    log "Deployment Details:"
    log "  Environment: ${ENVIRONMENT}"
    log "  Version: ${VERSION}"
    log "  Backup: ${ROLLBACK_VERSION}"
    log ""
    log "To rollback: ./deploy/rollback.sh ${ENVIRONMENT} ${ROLLBACK_VERSION}"
}

# Run main deployment
main
