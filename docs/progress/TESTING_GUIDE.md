# Testing Guide - The Beer Game

Complete guide for testing the system yourself.

---

## Table of Contents

1. [Quick Test](#quick-test-5-minutes)
2. [Comprehensive Testing](#comprehensive-testing)
3. [Performance Testing](#performance-testing)
4. [Manual Testing Scenarios](#manual-testing-scenarios)
5. [Automated Testing](#automated-testing)

---

## Quick Test (5 Minutes)

### Step 1: Start the Application

```bash
cd /home/trevor/Projects/The_Beer_Game

# Start all services
make up

# Wait for services to start (30-60 seconds)
# Watch the logs
make logs
```

**Expected Output**: Services starting, database connecting, backend ready

### Step 2: Verify Health

```bash
# Run health validation
./backend/scripts/validate_health.sh
```

**Expected Result**: All 10 health checks passing ✅

### Step 3: Access the Application

Open your browser to:
- **Frontend**: http://localhost:8088
- **API Docs**: http://localhost:8000/docs

**Login Credentials**:
- Email: `systemadmin@autonomy.ai`
- Password: `Autonomy@2025`

### Step 4: Create a Quick Game

1. Click "Create New Game"
2. Select "Quick Start Wizard"
3. Choose "Retail" industry, "Beginner" difficulty
4. Click "Use Recommended Template"
5. Review and launch

**Expected Result**: Game created and ready to play

### Step 5: Run a Quick Simulation

1. Open the created game
2. Click "Auto-play" or "Advance Round"
3. Watch the simulation run
4. View analytics dashboard

**Expected Result**: Game runs, metrics update, charts display

---

## Comprehensive Testing

### 1. Frontend Testing

#### A. Template Library
```bash
# Navigate to: http://localhost:8088/templates
```

**Test Checklist**:
- [ ] Templates load correctly
- [ ] Search works (try "retail", "manufacturing")
- [ ] Filter by category, industry, difficulty
- [ ] Toggle grid/list view
- [ ] Preview template (click "Details")
- [ ] Use template (click "Use")

#### B. Quick Start Wizard
```bash
# Navigate to: http://localhost:8088 → Create New Game → Quick Start
```

**Test Checklist**:
- [ ] Step 1: Select industry and difficulty
- [ ] Step 2: View recommended templates
- [ ] Step 3: Review configuration
- [ ] Launch game successfully
- [ ] Game appears in games list

#### C. Documentation Portal
```bash
# Navigate to: http://localhost:8088/documentation
```

**Test Checklist**:
- [ ] Navigation sidebar works
- [ ] Content displays correctly
- [ ] Search functionality works
- [ ] Code examples are formatted
- [ ] Links are clickable

#### D. Stochastic Analytics
```bash
# Navigate to: http://localhost:8088/stochastic
```

**Test Checklist**:
- [ ] Distribution preview works
- [ ] Monte Carlo configuration UI loads
- [ ] Start Monte Carlo simulation
- [ ] View results when complete
- [ ] Charts render correctly

#### E. Monitoring Dashboard
```bash
# Navigate to: http://localhost:8088/admin/monitoring
```

**Test Checklist**:
- [ ] Health status cards display
- [ ] Metrics charts render
- [ ] Auto-refresh works (5 seconds)
- [ ] All components show "healthy"

### 2. Backend API Testing

#### A. Health Endpoints

```bash
# Liveness
curl http://localhost:8000/api/v1/health/live

# Expected: {"status":"healthy","timestamp":"..."}

# Readiness
curl http://localhost:8000/api/v1/health/ready

# Expected: {"status":"healthy","components":{...}}

# Detailed
curl http://localhost:8000/api/v1/health/detailed

# Expected: Detailed component status
```

#### B. Template API

```bash
# List templates
curl http://localhost:8000/api/v1/templates?page=1&page_size=10

# Get featured
curl http://localhost:8000/api/v1/templates/featured?limit=5

# Search
curl "http://localhost:8000/api/v1/templates?query=retail&category=distribution"
```

#### C. Quick Start API

```bash
# Get recommendations
curl -X POST http://localhost:8000/api/v1/templates/quick-start \
  -H "Content-Type: application/json" \
  -d '{
    "industry": "retail",
    "difficulty": "beginner",
    "num_players": 4,
    "features": ["ai_agents"]
  }'
```

#### D. Metrics API

```bash
# Prometheus metrics
curl http://localhost:8000/api/v1/metrics

# JSON metrics
curl http://localhost:8000/api/v1/metrics/json
```

### 3. Database Testing

```bash
# Connect to database
docker compose exec db mysql -u root -p19890617 beer_game

# Test queries
SELECT COUNT(*) FROM templates;
SELECT COUNT(*) FROM supply_chain_configs;
SELECT COUNT(*) FROM games;
SELECT COUNT(*) FROM users;

# Expected: Templates > 30, Configs > 3, Users > 1
```

---

## Performance Testing

### 1. Load Testing with Locust

```bash
# Start Locust
cd backend/tests/load
locust -f locustfile.py --host http://localhost:8000

# Open browser: http://localhost:8089
# Configure:
#   - Number of users: 10 (start small)
#   - Spawn rate: 2 users/second
#   - Host: http://localhost:8000
# Click "Start Swarming"
```

**Metrics to Watch**:
- RPS (Requests per second)
- Response times (median, 95th percentile)
- Failure rate (should be <5%)
- Total requests

**Increase Load Gradually**:
1. Start with 10 users
2. Increase to 25 users
3. Increase to 50 users
4. Increase to 100 users

**Expected Performance**:
- 50 users: <500ms median response time
- 100 users: <2000ms average response time
- Error rate: <5%

### 2. Stress Testing

```bash
# Run async stress tests
cd backend/tests/load
python stress_test.py
```

**Expected Output**:
```
Test 1: Health endpoint - ✅ PASS
Test 2: Template listing - ✅ PASS
Test 3: Featured templates - ✅ PASS
Test 4: Template search - ✅ PASS
Test 5: Metrics endpoint - ✅ PASS

Overall: ✅ ALL TESTS PASSED
```

### 3. Concurrent User Testing

```bash
# Simulate 10 concurrent users
for i in {1..10}; do
  curl -s http://localhost:8000/api/v1/templates?page=1 > /dev/null &
done
wait

echo "All requests completed"
```

---

## Manual Testing Scenarios

### Scenario 1: Complete Game Workflow

**Objective**: Test end-to-end game creation and play

**Steps**:
1. Log in as admin
2. Navigate to "Supply Chain Configs"
3. Select "Default TBG" configuration
4. Create new game:
   - Name: "Test Game 1"
   - Max rounds: 12
5. Add 4 AI players:
   - Retailer: Naive agent
   - Wholesaler: Conservative agent
   - Distributor: ML Forecast agent
   - Factory: Optimizer agent
6. Start game
7. Auto-play all 12 rounds
8. View analytics:
   - Total cost
   - Bullwhip ratio
   - Service level
9. Export results to CSV

**Expected Results**:
- Game creates successfully
- All rounds complete without errors
- Analytics display correctly
- CSV export works

### Scenario 2: Template Usage Workflow

**Objective**: Test template library and usage

**Steps**:
1. Browse template library
2. Filter by "Retail" industry
3. Select "Steady Retail Demand" template
4. Preview template details
5. Click "Use Template"
6. Verify template configuration applied
7. Create game with template
8. Run simulation

**Expected Results**:
- Template loads correctly
- Configuration applied properly
- Game runs with expected behavior

### Scenario 3: Monte Carlo Simulation

**Objective**: Test stochastic analytics

**Steps**:
1. Create a game with stochastic configuration
2. Navigate to Stochastic Analytics
3. Configure Monte Carlo:
   - Number of runs: 50
   - Random seed: 42
4. Start simulation
5. Monitor progress (should take 2-5 minutes)
6. View results:
   - Mean metrics
   - Confidence intervals
   - Percentiles (P5, P50, P95)
7. Download results

**Expected Results**:
- Simulation completes successfully
- Results are statistically valid
- Confidence intervals are reasonable
- Downloads work

### Scenario 4: Concurrent Access

**Objective**: Test multi-user access

**Steps**:
1. Open 3 browser windows
2. Log in as different users in each (or same user)
3. In Window 1: Browse templates
4. In Window 2: Create a game
5. In Window 3: View analytics dashboard
6. Perform actions simultaneously in all windows

**Expected Results**:
- No conflicts or errors
- Each window operates independently
- Database consistency maintained

### Scenario 5: Error Recovery

**Objective**: Test error handling

**Steps**:
1. Try to access non-existent game: `/games/99999`
2. Try invalid login credentials
3. Submit invalid template configuration
4. Try to start game without players
5. Exceed rate limits (rapid API calls)

**Expected Results**:
- 404 errors for missing resources
- 401 errors for auth failures
- 422 errors for validation failures
- Appropriate error messages displayed
- No system crashes

---

## Automated Testing

### 1. Integration Tests

```bash
# Run full integration test suite
./backend/scripts/run_integration_tests.sh

# Expected: All 20+ tests passing
```

**Test Coverage**:
- Authentication workflows
- Template workflows
- Game creation workflows
- Monitoring endpoints
- Concurrent access
- Error recovery
- Data consistency
- Performance benchmarks

### 2. Run Tests with Coverage

```bash
# Generate coverage report
./backend/scripts/run_integration_tests.sh coverage

# View HTML report
open backend/htmlcov/index.html  # Mac
xdg-open backend/htmlcov/index.html  # Linux
```

### 3. Quick Smoke Tests

```bash
# Run quick tests (no performance benchmarks)
./backend/scripts/run_integration_tests.sh quick
```

### 4. Specific Test Class

```bash
# Test only template workflows
./backend/scripts/run_integration_tests.sh class TestTemplateWorkflow

# Test only authentication
./backend/scripts/run_integration_tests.sh class TestUserAuthenticationWorkflow
```

---

## Validation Checklist

After testing, verify:

### Frontend ✅
- [ ] All pages load without errors
- [ ] Forms submit correctly
- [ ] Charts render properly
- [ ] Navigation works
- [ ] Responsive design works

### Backend ✅
- [ ] All health checks pass
- [ ] API responses are fast (<2s)
- [ ] No errors in logs
- [ ] Database queries execute correctly
- [ ] Metrics are collected

### Performance ✅
- [ ] 50+ concurrent users supported
- [ ] Response times <2s average
- [ ] Error rate <5%
- [ ] No memory leaks
- [ ] Database connections stable

### Security ✅
- [ ] Authentication required
- [ ] Invalid credentials rejected
- [ ] CSRF protection works
- [ ] Secrets not exposed
- [ ] Rate limiting functional

### Data Integrity ✅
- [ ] Games save correctly
- [ ] Metrics calculate accurately
- [ ] No race conditions
- [ ] Rollback works
- [ ] Exports are correct

---

## Troubleshooting Test Issues

### Application Won't Start

```bash
# Check Docker status
docker compose ps

# View logs for errors
docker compose logs backend
docker compose logs frontend
docker compose logs db

# Restart services
make down
make up
```

### Tests Failing

```bash
# Check test database
mysql -u root -p19890617 -e "SHOW DATABASES LIKE 'beer_game_test';"

# Reset test environment
docker compose restart backend
```

### Performance Issues

```bash
# Check resource usage
docker stats

# Check database connections
docker compose exec db mysql -u root -p19890617 -e "SHOW PROCESSLIST;"

# Clear cache
docker system prune
```

### Port Conflicts

```bash
# Find process using port
lsof -i :8000
lsof -i :8088

# Kill process
kill -9 <PID>
```

---

## Test Reports

### Generate Test Report

```bash
# Run tests and generate report
./backend/scripts/run_integration_tests.sh coverage

# Create summary
cat > test_report.md << EOF
# Test Report - $(date +%Y-%m-%d)

## Summary
- Total Tests: 20+
- Passed: XX
- Failed: 0
- Coverage: XX%

## Performance
- Load Test: 100 users, <2s avg response
- Stress Test: All targets met
- Health Checks: All passing

## Status: ✅ ALL TESTS PASSED
EOF
```

---

## Next Steps After Testing

1. **If all tests pass**: System is ready for production deployment
2. **If some tests fail**: Review logs and fix issues
3. **For production**: Run load tests with production-like data
4. **For staging**: Deploy and test in staging environment

---

## Support

For testing issues:
- Check logs: `make logs`
- Review documentation: [DOCUMENTATION_INDEX.md](DOCUMENTATION_INDEX.md)
- See troubleshooting: [DEPLOYMENT.md](deploy/DEPLOYMENT.md#troubleshooting)

---

**Last Updated**: 2026-01-14
**Version**: 1.0
