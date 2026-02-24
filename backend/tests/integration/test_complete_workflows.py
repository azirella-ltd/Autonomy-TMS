#!/usr/bin/env python3
"""
Integration Tests - Complete User Workflows
Phase 6 Sprint 5: Production Deployment & Testing

End-to-end integration tests covering complete user workflows.
"""

import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typing import Dict, Any

from app.core.config import settings
from app.db.base import Base
from main import app


# Test database setup
TEST_DATABASE_URL = settings.DATABASE_URL.replace("beer_game", "beer_game_test")
test_engine = create_engine(TEST_DATABASE_URL)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def client():
    """Create async test client"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(scope="function")
def db_session():
    """Create test database session"""
    # Create all tables
    Base.metadata.create_all(bind=test_engine)

    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        # Drop all tables after test
        Base.metadata.drop_all(bind=test_engine)


class TestUserAuthenticationWorkflow:
    """Test complete user authentication workflow"""

    @pytest.mark.asyncio
    async def test_register_login_workflow(self, client: AsyncClient):
        """Test user registration and login"""
        # Step 1: Register new user
        register_data = {
            "email": "testuser@example.com",
            "password": "TestPassword123!",
            "full_name": "Test User"
        }

        response = await client.post("/api/v1/auth/register", json=register_data)
        assert response.status_code == 201
        user_data = response.json()
        assert user_data["email"] == register_data["email"]
        assert "id" in user_data

        # Step 2: Login with credentials
        login_data = {
            "username": register_data["email"],
            "password": register_data["password"]
        }

        response = await client.post("/api/v1/auth/login", data=login_data)
        assert response.status_code == 200
        token_data = response.json()
        assert "access_token" in token_data

        # Step 3: Verify token works
        headers = {"Authorization": f"Bearer {token_data['access_token']}"}
        response = await client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 200
        me_data = response.json()
        assert me_data["email"] == register_data["email"]

    @pytest.mark.asyncio
    async def test_invalid_credentials(self, client: AsyncClient):
        """Test login with invalid credentials"""
        login_data = {
            "username": "nonexistent@example.com",
            "password": "wrongpassword"
        }

        response = await client.post("/api/v1/auth/login", data=login_data)
        assert response.status_code == 401


class TestTemplateWorkflow:
    """Test complete template browsing and usage workflow"""

    @pytest.mark.asyncio
    async def test_browse_search_use_template(self, client: AsyncClient):
        """Test browsing, searching, and using templates"""
        # Step 1: List all templates
        response = await client.get("/api/v1/templates?page=1&page_size=20")
        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        assert "total" in data

        # Step 2: Search for specific templates
        response = await client.get(
            "/api/v1/templates?query=retail&category=distribution"
        )
        assert response.status_code == 200
        search_data = response.json()
        assert len(search_data["templates"]) > 0

        # Step 3: Get featured templates
        response = await client.get("/api/v1/templates/featured?limit=5")
        assert response.status_code == 200
        featured = response.json()
        assert len(featured) <= 5

        # Step 4: Use quick start wizard
        quick_start_data = {
            "industry": "retail",
            "difficulty": "beginner",
            "num_players": 4,
            "features": ["ai_agents"]
        }

        response = await client.post("/api/v1/templates/quick-start", json=quick_start_data)
        assert response.status_code == 200
        recommendations = response.json()
        assert "recommended_template" in recommendations
        assert "alternative_templates" in recommendations
        assert "next_steps" in recommendations

        # Step 5: Track template usage
        template_id = recommendations["recommended_template"]["id"]
        response = await client.post(f"/api/v1/templates/{template_id}/use")
        assert response.status_code == 200


class TestGameCreationWorkflow:
    """Test complete game creation workflow"""

    @pytest.mark.asyncio
    async def test_create_configure_start_game(self, client: AsyncClient):
        """Test creating, configuring, and starting a game"""
        # Step 1: Login as admin
        login_data = {
            "username": "systemadmin@autonomy.ai",
            "password": "Autonomy@2025"
        }
        response = await client.post("/api/v1/auth/login", data=login_data)
        assert response.status_code == 200
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Step 2: Get supply chain configs
        response = await client.get("/api/v1/supply-chain-configs", headers=headers)
        assert response.status_code == 200
        configs = response.json()
        assert len(configs) > 0
        config_id = configs[0]["id"]

        # Step 3: Create new game
        game_data = {
            "name": "Integration Test Game",
            "supply_chain_config_id": config_id,
            "max_periods": 24
        }
        response = await client.post("/api/v1/mixed-scenarios/", json=game_data, headers=headers)
        assert response.status_code == 201
        game = response.json()
        game_id = game["id"]

        # Step 4: Add players
        player_data = {
            "node_id": 1,
            "player_type": "ai",
            "agent_strategy": "naive"
        }
        response = await client.post(
            f"/api/v1/mixed-scenarios/{game_id}/players",
            json=player_data,
            headers=headers
        )
        assert response.status_code == 201

        # Step 5: Start game
        response = await client.post(f"/api/v1/mixed-scenarios/{game_id}/start", headers=headers)
        assert response.status_code == 200

        # Step 6: Verify game state
        response = await client.get(f"/api/v1/mixed-scenarios/{game_id}/state", headers=headers)
        assert response.status_code == 200
        state = response.json()
        assert state["status"] == "active"


class TestMonitoringWorkflow:
    """Test monitoring and health check workflow"""

    @pytest.mark.asyncio
    async def test_health_checks(self, client: AsyncClient):
        """Test all health check endpoints"""
        # Test liveness probe
        response = await client.get("/api/v1/health/live")
        assert response.status_code == 200
        live_data = response.json()
        assert live_data["status"] == "healthy"

        # Test readiness probe
        response = await client.get("/api/v1/health/ready")
        assert response.status_code == 200
        ready_data = response.json()
        assert ready_data["status"] in ["healthy", "degraded"]

        # Test detailed health
        response = await client.get("/api/v1/health/detailed")
        assert response.status_code == 200
        detailed_data = response.json()
        assert "components" in detailed_data
        assert "database" in detailed_data["components"]

    @pytest.mark.asyncio
    async def test_metrics_endpoints(self, client: AsyncClient):
        """Test metrics collection endpoints"""
        # Test Prometheus metrics
        response = await client.get("/api/v1/metrics")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"

        # Test JSON metrics
        response = await client.get("/api/v1/metrics/json")
        assert response.status_code == 200
        metrics = response.json()
        assert "metrics" in metrics


class TestConcurrentAccessWorkflow:
    """Test concurrent user access scenarios"""

    @pytest.mark.asyncio
    async def test_multiple_users_browsing_templates(self, client: AsyncClient):
        """Test multiple users browsing templates concurrently"""
        # Simulate 10 concurrent users browsing templates
        tasks = []
        for i in range(10):
            task = client.get(f"/api/v1/templates?page={i % 5 + 1}&page_size=20")
            tasks.append(task)

        responses = await asyncio.gather(*tasks)

        # All requests should succeed
        for response in responses:
            assert response.status_code == 200
            data = response.json()
            assert "templates" in data

    @pytest.mark.asyncio
    async def test_concurrent_game_operations(self, client: AsyncClient):
        """Test concurrent game state reads"""
        # Login
        login_data = {
            "username": "systemadmin@autonomy.ai",
            "password": "Autonomy@2025"
        }
        response = await client.post("/api/v1/auth/login", data=login_data)
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create a game first
        game_data = {
            "name": "Concurrent Test Game",
            "supply_chain_config_id": 1,
            "max_periods": 24
        }
        response = await client.post("/api/v1/mixed-scenarios/", json=game_data, headers=headers)
        game_id = response.json()["id"]

        # Start game
        await client.post(f"/api/v1/mixed-scenarios/{game_id}/start", headers=headers)

        # Simulate 10 concurrent reads
        tasks = []
        for _ in range(10):
            task = client.get(f"/api/v1/mixed-scenarios/{game_id}/state", headers=headers)
            tasks.append(task)

        responses = await asyncio.gather(*tasks)

        # All reads should succeed with consistent state
        states = [response.json() for response in responses]
        first_state = states[0]
        for state in states[1:]:
            assert state["id"] == first_state["id"]
            assert state["status"] == first_state["status"]


class TestErrorRecoveryWorkflow:
    """Test error handling and recovery scenarios"""

    @pytest.mark.asyncio
    async def test_invalid_game_operations(self, client: AsyncClient):
        """Test error handling for invalid game operations"""
        # Login
        login_data = {
            "username": "systemadmin@autonomy.ai",
            "password": "Autonomy@2025"
        }
        response = await client.post("/api/v1/auth/login", data=login_data)
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Try to access non-existent game
        response = await client.get("/api/v1/mixed-scenarios/99999/state", headers=headers)
        assert response.status_code == 404

        # Try to start game that doesn't exist
        response = await client.post("/api/v1/mixed-scenarios/99999/start", headers=headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_data_handling(self, client: AsyncClient):
        """Test handling of invalid input data"""
        # Invalid template search parameters
        response = await client.get("/api/v1/templates?page=-1")
        assert response.status_code == 422

        # Invalid quick start data
        invalid_data = {
            "industry": "invalid_industry",
            "difficulty": "invalid_difficulty"
        }
        response = await client.post("/api/v1/templates/quick-start", json=invalid_data)
        assert response.status_code == 422


class TestDataConsistencyWorkflow:
    """Test data consistency under various scenarios"""

    @pytest.mark.asyncio
    async def test_template_usage_counter_consistency(self, client: AsyncClient):
        """Test that template usage counter increments correctly"""
        # Get initial usage count
        response = await client.get("/api/v1/templates/featured?limit=1")
        templates = response.json()
        if len(templates) > 0:
            template_id = templates[0]["id"]
            initial_count = templates[0]["usage_count"]

            # Use template multiple times
            for _ in range(5):
                await client.post(f"/api/v1/templates/{template_id}/use")

            # Get updated template
            response = await client.get(f"/api/v1/templates/{template_id}")
            updated_template = response.json()

            # Usage count should have increased by 5
            assert updated_template["usage_count"] == initial_count + 5

    @pytest.mark.asyncio
    async def test_tutorial_progress_persistence(self, client: AsyncClient):
        """Test tutorial progress is saved and retrieved correctly"""
        # Login
        login_data = {
            "username": "systemadmin@autonomy.ai",
            "password": "Autonomy@2025"
        }
        response = await client.post("/api/v1/auth/login", data=login_data)
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Start tutorial
        tutorial_data = {
            "tutorial_id": "getting-started",
            "total_steps": 5,
            "current_step": 0
        }
        response = await client.post(
            "/api/v1/templates/tutorials/progress",
            json=tutorial_data,
            headers=headers
        )
        assert response.status_code == 201

        # Update progress
        update_data = {
            "current_step": 3,
            "completed": False
        }
        response = await client.put(
            "/api/v1/templates/tutorials/progress/getting-started",
            json=update_data,
            headers=headers
        )
        assert response.status_code == 200

        # Retrieve progress
        response = await client.get(
            "/api/v1/templates/tutorials/progress/getting-started",
            headers=headers
        )
        assert response.status_code == 200
        progress = response.json()
        assert progress["current_step"] == 3
        assert progress["completed"] is False


# Performance benchmarks
class TestPerformanceBenchmarks:
    """Performance benchmark tests"""

    @pytest.mark.asyncio
    async def test_template_list_performance(self, client: AsyncClient):
        """Test template listing performance"""
        import time

        start = time.time()
        response = await client.get("/api/v1/templates?page=1&page_size=20")
        duration = time.time() - start

        assert response.status_code == 200
        assert duration < 1.0  # Should complete in less than 1 second

    @pytest.mark.asyncio
    async def test_search_performance(self, client: AsyncClient):
        """Test search performance"""
        import time

        start = time.time()
        response = await client.get("/api/v1/templates?query=retail&category=distribution")
        duration = time.time() - start

        assert response.status_code == 200
        assert duration < 1.5  # Should complete in less than 1.5 seconds


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
