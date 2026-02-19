# Integration Tests

Comprehensive end-to-end integration tests for The Beer Game platform.

## Overview

These integration tests validate complete user workflows and system behavior under various scenarios including:

- User authentication workflows
- Template browsing and usage
- Game creation and management
- Monitoring and health checks
- Concurrent access scenarios
- Error handling and recovery
- Data consistency validation
- Performance benchmarks

## Test Structure

### Test Classes

1. **TestUserAuthenticationWorkflow**
   - User registration and login
   - Token validation
   - Invalid credentials handling

2. **TestTemplateWorkflow**
   - Template browsing and search
   - Quick start wizard
   - Template usage tracking

3. **TestGameCreationWorkflow**
   - Complete game creation flow
   - Player assignment
   - Game initialization and state management

4. **TestMonitoringWorkflow**
   - Health check endpoints (live, ready, detailed)
   - Metrics collection (Prometheus and JSON)

5. **TestConcurrentAccessWorkflow**
   - Multiple users browsing templates
   - Concurrent game state reads
   - Database transaction consistency

6. **TestErrorRecoveryWorkflow**
   - Invalid game operations
   - Invalid input data handling
   - 404 and 422 error responses

7. **TestDataConsistencyWorkflow**
   - Template usage counter accuracy
   - Tutorial progress persistence
   - Transaction isolation

8. **TestPerformanceBenchmarks**
   - Template listing performance (<1s)
   - Search performance (<1.5s)

## Running Tests

### Prerequisites

1. Install test dependencies:
```bash
cd backend
pip install pytest pytest-asyncio httpx
```

2. Set up test database:
```bash
# Create test database
mysql -u root -p -e "CREATE DATABASE autonomy_test;"
mysql -u root -p -e "GRANT ALL PRIVILEGES ON autonomy_test.* TO 'autonomy_user'@'%';"
```

3. Ensure backend is running:
```bash
make up
```

### Run All Tests

```bash
cd backend
pytest tests/integration/test_complete_workflows.py -v
```

### Run Specific Test Class

```bash
pytest tests/integration/test_complete_workflows.py::TestTemplateWorkflow -v
```

### Run Specific Test

```bash
pytest tests/integration/test_complete_workflows.py::TestTemplateWorkflow::test_browse_search_use_template -v
```

### Run with Coverage

```bash
pytest tests/integration/test_complete_workflows.py --cov=app --cov-report=html
```

### Run Performance Benchmarks Only

```bash
pytest tests/integration/test_complete_workflows.py::TestPerformanceBenchmarks -v
```

## Test Patterns

### Async Tests

All tests use `pytest-asyncio` for async/await support:

```python
@pytest.mark.asyncio
async def test_example(self, client: AsyncClient):
    response = await client.get("/api/v1/endpoint")
    assert response.status_code == 200
```

### Database Fixtures

Tests use function-scoped database fixtures that:
- Create tables before each test
- Clean up after each test
- Ensure test isolation

```python
@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=test_engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)
```

### Authentication Pattern

Tests that require authentication follow this pattern:

```python
# Login
login_data = {
    "username": "systemadmin@autonomy.ai",
    "password": "Autonomy@2025"
}
response = await client.post("/api/v1/auth/login", data=login_data)
token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Authenticated request
response = await client.get("/api/v1/endpoint", headers=headers)
```

### Concurrent Testing Pattern

Tests for concurrent access use `asyncio.gather`:

```python
# Create concurrent tasks
tasks = []
for i in range(10):
    task = client.get(f"/api/v1/endpoint?param={i}")
    tasks.append(task)

# Execute concurrently
responses = await asyncio.gather(*tasks)

# Validate all responses
for response in responses:
    assert response.status_code == 200
```

## Expected Results

### Success Criteria

- All tests pass (100% success rate)
- No database deadlocks or transaction errors
- Response times within performance targets
- Data consistency maintained under concurrent access

### Performance Targets

- Template listing: <1.0 second
- Search queries: <1.5 seconds
- Health checks: <100ms
- Game state reads: <500ms

## CI/CD Integration

These tests are designed to run in CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run Integration Tests
  run: |
    cd backend
    pytest tests/integration/test_complete_workflows.py -v --tb=short
  env:
    DATABASE_URL: ${{ secrets.TEST_DATABASE_URL }}
```

## Troubleshooting

### Database Connection Issues

If tests fail with database connection errors:

```bash
# Verify test database exists
mysql -u root -p -e "SHOW DATABASES LIKE 'beer_game_test';"

# Check connection from Python
python -c "from sqlalchemy import create_engine; engine = create_engine('mysql+pymysql://beer_user:beer_password@localhost/beer_game_test'); print(engine.connect())"
```

### Fixture Cleanup Issues

If tests leave residual data:

```bash
# Manually drop test database
mysql -u root -p -e "DROP DATABASE IF EXISTS beer_game_test;"
mysql -u root -p -e "CREATE DATABASE beer_game_test;"
```

### Authentication Failures

If authentication tests fail:

```bash
# Ensure default admin exists
cd backend
python -c "from app.db.init_db import init_db; init_db()"
```

## Test Data

Tests use:
- Default system admin: `systemadmin@autonomy.ai` / `Autonomy@2025`
- Test user: `testuser@example.com` / `TestPassword123!`
- Default supply chain configs from seed data

## Contributing

When adding new integration tests:

1. Follow existing patterns for consistency
2. Use descriptive test names that explain what is being tested
3. Include docstrings explaining the test scenario
4. Clean up resources in fixtures
5. Add performance assertions where appropriate
6. Update this README with new test classes

## References

- pytest documentation: https://docs.pytest.org/
- pytest-asyncio: https://pytest-asyncio.readthedocs.io/
- httpx (async client): https://www.python-httpx.org/
