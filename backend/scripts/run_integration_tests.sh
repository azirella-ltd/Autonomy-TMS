#!/bin/bash
#
# Integration Test Runner
# Phase 6 Sprint 5: Production Deployment & Testing
#
# Runs complete integration test suite with reporting
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=================================="
echo "Integration Test Runner"
echo "=================================="
echo ""

# Check if backend is running
echo -n "Checking backend status... "
if curl -s http://localhost:8000/api/v1/health/live > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Backend is running${NC}"
else
    echo -e "${RED}✗ Backend is not running${NC}"
    echo "Please start the backend with: make up"
    exit 1
fi

# Check test database
echo -n "Checking test database... "
if mysql -u autonomy_user -pbeer_password -e "USE autonomy_test;" 2>/dev/null; then
    echo -e "${GREEN}✓ Test database exists${NC}"
else
    echo -e "${YELLOW}⚠ Test database does not exist, creating...${NC}"
    mysql -u root -p19890617 -e "CREATE DATABASE IF NOT EXISTS autonomy_test;" 2>/dev/null || true
    mysql -u root -p19890617 -e "GRANT ALL PRIVILEGES ON autonomy_test.* TO 'autonomy_user'@'%';" 2>/dev/null || true
    echo -e "${GREEN}✓ Test database created${NC}"
fi

# Install test dependencies
echo -n "Checking test dependencies... "
pip list | grep -q pytest && pip list | grep -q httpx
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Dependencies installed${NC}"
else
    echo -e "${YELLOW}⚠ Installing test dependencies...${NC}"
    pip install pytest pytest-asyncio httpx pytest-cov
    echo -e "${GREEN}✓ Dependencies installed${NC}"
fi

echo ""
echo "=================================="
echo "Running Integration Tests"
echo "=================================="
echo ""

# Run tests with different options based on arguments
if [ "$1" = "coverage" ]; then
    echo "Running tests with coverage report..."
    pytest tests/integration/test_complete_workflows.py \
        -v \
        --tb=short \
        --cov=app \
        --cov-report=term-missing \
        --cov-report=html:htmlcov

    echo ""
    echo -e "${GREEN}Coverage report generated at: htmlcov/index.html${NC}"

elif [ "$1" = "quick" ]; then
    echo "Running quick tests (no performance benchmarks)..."
    pytest tests/integration/test_complete_workflows.py \
        -v \
        --tb=short \
        -k "not Performance"

elif [ "$1" = "performance" ]; then
    echo "Running performance benchmarks only..."
    pytest tests/integration/test_complete_workflows.py::TestPerformanceBenchmarks \
        -v \
        --tb=short

elif [ "$1" = "concurrent" ]; then
    echo "Running concurrent access tests only..."
    pytest tests/integration/test_complete_workflows.py::TestConcurrentAccessWorkflow \
        -v \
        --tb=short

elif [ "$1" = "class" ] && [ -n "$2" ]; then
    echo "Running test class: $2"
    pytest "tests/integration/test_complete_workflows.py::$2" \
        -v \
        --tb=short

else
    echo "Running full test suite..."
    pytest tests/integration/test_complete_workflows.py \
        -v \
        --tb=short
fi

# Capture exit code
TEST_EXIT_CODE=$?

echo ""
echo "=================================="
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed${NC}"
else
    echo -e "${RED}✗ Some tests failed${NC}"
fi
echo "=================================="

# Cleanup test database
echo ""
echo -n "Cleaning up test database... "
mysql -u root -p19890617 -e "DROP DATABASE IF EXISTS autonomy_test;" 2>/dev/null || true
mysql -u root -p19890617 -e "CREATE DATABASE autonomy_test;" 2>/dev/null || true
echo -e "${GREEN}✓ Cleanup complete${NC}"

exit $TEST_EXIT_CODE
