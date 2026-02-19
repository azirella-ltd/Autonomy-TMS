#!/bin/bash
#
# Health Check Validation Script
# Phase 6 Sprint 5: Production Deployment & Testing
#
# Comprehensive health check validation for deployment verification
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
BASE_URL="${1:-http://localhost:8000}"
MAX_RETRIES=30
RETRY_INTERVAL=5

echo -e "${BLUE}=================================="
echo "Health Check Validation"
echo "==================================${NC}"
echo ""
echo "Base URL: ${BASE_URL}"
echo ""

# Function to log with timestamp
log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Function to check endpoint
check_endpoint() {
    local endpoint=$1
    local expected_status=$2
    local max_retries=$3

    log "Checking ${endpoint}..."

    for i in $(seq 1 $max_retries); do
        response=$(curl -s -w "\n%{http_code}" "${BASE_URL}${endpoint}" 2>/dev/null)
        status_code=$(echo "$response" | tail -n1)
        body=$(echo "$response" | head -n-1)

        if [ "$status_code" = "$expected_status" ]; then
            log "${GREEN}✓ ${endpoint} - Status ${status_code}${NC}"
            echo "$body"
            return 0
        fi

        if [ $i -lt $max_retries ]; then
            log "${YELLOW}Attempt $i/$max_retries failed (status: ${status_code}), retrying...${NC}"
            sleep $RETRY_INTERVAL
        fi
    done

    log "${RED}✗ ${endpoint} - Failed after ${max_retries} attempts${NC}"
    return 1
}

# Function to validate JSON response
validate_json_field() {
    local json=$1
    local field=$2
    local expected=$3

    value=$(echo "$json" | python3 -c "import sys, json; print(json.load(sys.stdin).get('$field', ''))")

    if [ "$value" = "$expected" ]; then
        log "${GREEN}✓ Field '$field' = '$expected'${NC}"
        return 0
    else
        log "${RED}✗ Field '$field' = '$value', expected '$expected'${NC}"
        return 1
    fi
}

# Track overall status
OVERALL_STATUS=0

# Test 1: Liveness Probe
echo ""
log "${BLUE}Test 1: Liveness Probe${NC}"
response=$(check_endpoint "/api/v1/health/live" "200" $MAX_RETRIES)
if [ $? -eq 0 ]; then
    validate_json_field "$response" "status" "healthy"
else
    OVERALL_STATUS=1
fi

# Test 2: Readiness Probe
echo ""
log "${BLUE}Test 2: Readiness Probe${NC}"
response=$(check_endpoint "/api/v1/health/ready" "200" $MAX_RETRIES)
if [ $? -eq 0 ]; then
    validate_json_field "$response" "status" "healthy"
else
    OVERALL_STATUS=1
fi

# Test 3: Detailed Health Check
echo ""
log "${BLUE}Test 3: Detailed Health Check${NC}"
response=$(check_endpoint "/api/v1/health/detailed" "200" 5)
if [ $? -eq 0 ]; then
    # Check database component
    db_status=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('components', {}).get('database', ''))" 2>/dev/null)
    if [ "$db_status" = "healthy" ]; then
        log "${GREEN}✓ Database component is healthy${NC}"
    else
        log "${RED}✗ Database component status: ${db_status}${NC}"
        OVERALL_STATUS=1
    fi
else
    OVERALL_STATUS=1
fi

# Test 4: Metrics Endpoint
echo ""
log "${BLUE}Test 4: Metrics Endpoint${NC}"
response=$(check_endpoint "/api/v1/metrics" "200" 5)
if [ $? -ne 0 ]; then
    OVERALL_STATUS=1
fi

# Test 5: JSON Metrics
echo ""
log "${BLUE}Test 5: JSON Metrics${NC}"
response=$(check_endpoint "/api/v1/metrics/json" "200" 5)
if [ $? -eq 0 ]; then
    # Verify metrics structure
    metrics=$(echo "$response" | python3 -c "import sys, json; print('metrics' in json.load(sys.stdin))" 2>/dev/null)
    if [ "$metrics" = "True" ]; then
        log "${GREEN}✓ Metrics structure valid${NC}"
    else
        log "${RED}✗ Invalid metrics structure${NC}"
        OVERALL_STATUS=1
    fi
else
    OVERALL_STATUS=1
fi

# Test 6: Database Connectivity
echo ""
log "${BLUE}Test 6: Database Connectivity${NC}"
if docker compose exec -T backend python -c "
from app.db.session import SessionLocal
db = SessionLocal()
result = db.execute('SELECT 1').scalar()
assert result == 1
" 2>/dev/null; then
    log "${GREEN}✓ Database connectivity verified${NC}"
else
    log "${RED}✗ Database connectivity failed${NC}"
    OVERALL_STATUS=1
fi

# Test 7: Template API
echo ""
log "${BLUE}Test 7: Template API${NC}"
response=$(check_endpoint "/api/v1/templates?page=1&page_size=5" "200" 5)
if [ $? -eq 0 ]; then
    # Verify response structure
    has_templates=$(echo "$response" | python3 -c "import sys, json; print('templates' in json.load(sys.stdin))" 2>/dev/null)
    if [ "$has_templates" = "True" ]; then
        log "${GREEN}✓ Template API working${NC}"
    else
        log "${RED}✗ Template API response invalid${NC}"
        OVERALL_STATUS=1
    fi
else
    OVERALL_STATUS=1
fi

# Test 8: Featured Templates
echo ""
log "${BLUE}Test 8: Featured Templates${NC}"
response=$(check_endpoint "/api/v1/templates/featured?limit=5" "200" 5)
if [ $? -ne 0 ]; then
    OVERALL_STATUS=1
fi

# Test 9: Supply Chain Configs
echo ""
log "${BLUE}Test 9: Supply Chain Configs${NC}"
response=$(check_endpoint "/api/v1/supply-chain-configs" "200" 5)
if [ $? -ne 0 ]; then
    OVERALL_STATUS=1
fi

# Test 10: API Documentation
echo ""
log "${BLUE}Test 10: API Documentation${NC}"
response=$(check_endpoint "/docs" "200" 5)
if [ $? -ne 0 ]; then
    OVERALL_STATUS=1
fi

# Performance Tests
echo ""
log "${BLUE}Performance Tests${NC}"

# Test response times
echo ""
log "Measuring response times..."

measure_response_time() {
    local endpoint=$1
    local threshold_ms=$2

    start=$(date +%s%N)
    curl -s "${BASE_URL}${endpoint}" > /dev/null 2>&1
    end=$(date +%s%N)

    duration_ms=$(( (end - start) / 1000000 ))

    if [ $duration_ms -lt $threshold_ms ]; then
        log "${GREEN}✓ ${endpoint}: ${duration_ms}ms < ${threshold_ms}ms${NC}"
        return 0
    else
        log "${RED}✗ ${endpoint}: ${duration_ms}ms >= ${threshold_ms}ms${NC}"
        return 1
    fi
}

# Health check should be fast (<100ms)
measure_response_time "/api/v1/health/live" 100
if [ $? -ne 0 ]; then
    OVERALL_STATUS=1
fi

# Template listing should be reasonable (<2000ms)
measure_response_time "/api/v1/templates?page=1&page_size=20" 2000
if [ $? -ne 0 ]; then
    OVERALL_STATUS=1
fi

# Concurrent Request Test
echo ""
log "${BLUE}Concurrent Request Test${NC}"

log "Testing 10 concurrent health check requests..."
for i in {1..10}; do
    curl -s "${BASE_URL}/api/v1/health/live" > /dev/null 2>&1 &
done
wait

log "${GREEN}✓ Concurrent requests completed${NC}"

# Memory Check
echo ""
log "${BLUE}Resource Usage${NC}"

# Check container memory usage
if command -v docker &> /dev/null; then
    backend_memory=$(docker stats --no-stream --format "{{.MemUsage}}" autonomy-backend 2>/dev/null | cut -d '/' -f 1)
    if [ -n "$backend_memory" ]; then
        log "Backend memory usage: ${backend_memory}"
    fi
fi

# Summary
echo ""
echo -e "${BLUE}=================================="
echo "Summary"
echo "==================================${NC}"

if [ $OVERALL_STATUS -eq 0 ]; then
    echo -e "${GREEN}✓✓✓ All health checks passed ✓✓✓${NC}"
    echo ""
    echo "The application is healthy and ready to serve traffic."
    exit 0
else
    echo -e "${RED}✗✗✗ Some health checks failed ✗✗✗${NC}"
    echo ""
    echo "Please review the failed checks above and investigate."
    exit 1
fi
