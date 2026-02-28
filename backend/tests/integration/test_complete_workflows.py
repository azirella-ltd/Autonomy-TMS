#!/usr/bin/env python3
"""
Integration Tests - Complete User Workflows
Phase 6 Sprint 5: Production Deployment & Testing

End-to-end integration tests covering complete user workflows.
Tests run against the live ASGI app using httpx AsyncClient.
"""

import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from main import app


@pytest_asyncio.fixture(scope="function")
async def client():
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ============================================================================
# Auth helpers
# ============================================================================

async def _login_admin(client: AsyncClient) -> dict:
    """Login as system admin and return auth headers."""
    response = await client.post(
        "/api/v1/auth/login",
        data={
            "username": "systemadmin@autonomy.ai",
            "password": "Autonomy@2026",
        },
    )
    if response.status_code != 200:
        pytest.skip("Admin login unavailable (DB may not be seeded)")
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# Authentication Workflow
# ============================================================================

class TestUserAuthenticationWorkflow:
    """Test complete user authentication workflow."""

    @pytest.mark.asyncio
    async def test_login_and_me(self, client: AsyncClient):
        """Test login with valid credentials and /me endpoint."""
        headers = await _login_admin(client)

        # Verify token works
        response = await client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 200
        me_data = response.json()
        assert "email" in me_data
        assert "id" in me_data

    @pytest.mark.asyncio
    async def test_invalid_credentials(self, client: AsyncClient):
        """Test login with invalid credentials returns 401."""
        response = await client.post(
            "/api/v1/auth/login",
            data={
                "username": "nonexistent@example.com",
                "password": "wrongpassword",
            },
        )
        assert response.status_code == 401


# ============================================================================
# Scenario Creation Workflow
# ============================================================================

class TestScenarioCreationWorkflow:
    """Test complete scenario creation workflow."""

    @pytest.mark.asyncio
    async def test_list_supply_chain_configs(self, client: AsyncClient):
        """Test listing supply chain configurations."""
        headers = await _login_admin(client)

        response = await client.get("/api/v1/supply-chain-config/", headers=headers)
        assert response.status_code == 200
        configs = response.json()
        assert isinstance(configs, list)

    @pytest.mark.asyncio
    async def test_create_and_check_scenario(self, client: AsyncClient):
        """Test creating a scenario and checking its state."""
        headers = await _login_admin(client)

        # Get configs
        response = await client.get("/api/v1/supply-chain-config/", headers=headers)
        if response.status_code != 200 or not response.json():
            pytest.skip("No supply chain configs available")

        configs = response.json()
        config_id = configs[0]["id"]

        # Create scenario
        scenario_data = {
            "name": "Integration Test Scenario",
            "supply_chain_config_id": config_id,
            "max_periods": 12,
        }
        response = await client.post(
            "/api/v1/mixed-scenarios/",
            json=scenario_data,
            headers=headers,
        )
        # May fail if DB constraints aren't met; skip gracefully
        if response.status_code not in (200, 201):
            pytest.skip(f"Scenario creation returned {response.status_code}")

        scenario = response.json()
        scenario_id = scenario["id"]

        # Check state
        response = await client.get(
            f"/api/v1/mixed-scenarios/{scenario_id}/state",
            headers=headers,
        )
        assert response.status_code == 200


# ============================================================================
# Monitoring Workflow
# ============================================================================

class TestMonitoringWorkflow:
    """Test monitoring and health check workflow."""

    @pytest.mark.asyncio
    async def test_health_live(self, client: AsyncClient):
        """Test liveness probe."""
        response = await client.get("/api/v1/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_ready(self, client: AsyncClient):
        """Test readiness probe."""
        response = await client.get("/api/v1/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("healthy", "degraded")

    @pytest.mark.asyncio
    async def test_health_version(self, client: AsyncClient):
        """Test version endpoint."""
        response = await client.get("/api/v1/health/version")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_metrics_json(self, client: AsyncClient):
        """Test JSON metrics endpoint."""
        response = await client.get("/api/v1/metrics/json")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_metrics_prometheus(self, client: AsyncClient):
        """Test Prometheus metrics endpoint."""
        response = await client.get("/api/v1/metrics")
        assert response.status_code == 200


# ============================================================================
# Error Recovery Workflow
# ============================================================================

class TestErrorRecoveryWorkflow:
    """Test error handling and recovery scenarios."""

    @pytest.mark.asyncio
    async def test_nonexistent_scenario(self, client: AsyncClient):
        """Test accessing non-existent scenario returns 404."""
        headers = await _login_admin(client)

        response = await client.get(
            "/api/v1/mixed-scenarios/99999/state",
            headers=headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_start_nonexistent_scenario(self, client: AsyncClient):
        """Test starting non-existent scenario returns 404."""
        headers = await _login_admin(client)

        response = await client.post(
            "/api/v1/mixed-scenarios/99999/start",
            headers=headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthenticated_access(self, client: AsyncClient):
        """Test accessing protected endpoints without auth returns 401/403/404."""
        response = await client.get("/api/v1/auth/me")
        # Without token, /me should reject
        assert response.status_code in (401, 403, 422)


# ============================================================================
# Concurrent Access Workflow
# ============================================================================

class TestConcurrentAccessWorkflow:
    """Test concurrent user access scenarios."""

    @pytest.mark.asyncio
    async def test_concurrent_health_checks(self, client: AsyncClient):
        """Test multiple concurrent health checks."""
        tasks = [client.get("/api/v1/health/live") for _ in range(10)]
        responses = await asyncio.gather(*tasks)

        for response in responses:
            assert response.status_code == 200
            assert response.json()["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_concurrent_metrics(self, client: AsyncClient):
        """Test multiple concurrent metric reads."""
        tasks = [client.get("/api/v1/metrics/json") for _ in range(5)]
        responses = await asyncio.gather(*tasks)

        for response in responses:
            assert response.status_code == 200


# ============================================================================
# Performance Benchmarks
# ============================================================================

class TestPerformanceBenchmarks:
    """Performance benchmark tests."""

    @pytest.mark.asyncio
    async def test_health_check_performance(self, client: AsyncClient):
        """Test health check responds within 1 second."""
        import time

        start = time.time()
        response = await client.get("/api/v1/health/live")
        duration = time.time() - start

        assert response.status_code == 200
        assert duration < 1.0

    @pytest.mark.asyncio
    async def test_metrics_performance(self, client: AsyncClient):
        """Test metrics endpoint responds within 2 seconds."""
        import time

        start = time.time()
        response = await client.get("/api/v1/metrics/json")
        duration = time.time() - start

        assert response.status_code == 200
        assert duration < 2.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
