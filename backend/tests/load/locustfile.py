"""
Locust Load Testing Suite
Phase 6 Sprint 5: Production Deployment & Testing

Load testing for API endpoints, concurrent users, and stress testing.
Targets:
- 100 concurrent users
- 1000 requests/minute
- <2s average response time
- <5% error rate
"""

from locust import HttpUser, task, between, SequentialTaskSet
import random
import json


class UserBehavior(SequentialTaskSet):
    """Sequential user behavior simulating realistic workflows"""

    def on_start(self):
        """Login and setup"""
        # Login
        response = self.client.post("/api/v1/auth/login", data={
            "username": "testuser@example.com",
            "password": "testpassword"
        })
        if response.status_code == 200:
            self.token = response.json().get("access_token")
        else:
            # Use default credentials
            response = self.client.post("/api/v1/auth/login", data={
                "username": "systemadmin@autonomy.ai",
                "password": "Autonomy@2025"
            })
            if response.status_code == 200:
                self.token = response.json().get("access_token")

    @task
    def browse_templates(self):
        """Browse template library"""
        # List templates
        self.client.get("/api/v1/templates?page=1&page_size=20")

        # Get featured templates
        self.client.get("/api/v1/templates/featured?limit=10")

        # Get popular templates
        self.client.get("/api/v1/templates/popular?limit=10")

    @task
    def search_templates(self):
        """Search templates with filters"""
        categories = ["distribution", "scenario", "game"]
        industries = ["retail", "manufacturing", "logistics"]
        difficulties = ["beginner", "intermediate", "advanced"]

        category = random.choice(categories)
        industry = random.choice(industries)
        difficulty = random.choice(difficulties)

        self.client.get(
            f"/api/v1/templates?category={category}&industry={industry}&difficulty={difficulty}"
        )

    @task
    def use_quick_start(self):
        """Use quick start wizard"""
        payload = {
            "industry": random.choice(["retail", "manufacturing", "logistics"]),
            "difficulty": random.choice(["beginner", "intermediate"]),
            "features": [],
            "use_monte_carlo": False,
            "num_scenario_users": random.randint(2, 6)
        }

        self.client.post("/api/v1/templates/quick-start", json=payload)

    @task
    def check_health(self):
        """Check system health"""
        self.client.get("/api/v1/health")
        self.client.get("/api/v1/health/live")
        self.client.get("/api/v1/health/ready")

    @task
    def view_metrics(self):
        """View system metrics"""
        self.client.get("/api/v1/metrics/json")

    @task
    def manage_preferences(self):
        """Manage user preferences"""
        # Get preferences
        self.client.get("/api/v1/templates/preferences")

        # Update preferences
        payload = {
            "theme": random.choice(["light", "dark"]),
            "show_tutorials": random.choice([True, False]),
            "show_tips": True
        }
        self.client.put("/api/v1/templates/preferences", json=payload)


class TemplateUser(HttpUser):
    """User focused on template operations"""
    tasks = [UserBehavior]
    wait_time = between(1, 3)
    host = "http://localhost:8000"


class HealthCheckUser(HttpUser):
    """User performing health checks"""
    wait_time = between(0.5, 1)
    host = "http://localhost:8000"

    @task(10)
    def check_health(self):
        self.client.get("/api/v1/health")

    @task(5)
    def check_liveness(self):
        self.client.get("/api/v1/health/live")

    @task(5)
    def check_readiness(self):
        self.client.get("/api/v1/health/ready")

    @task(3)
    def check_metrics(self):
        self.client.get("/api/v1/metrics/json")


class APIStressUser(HttpUser):
    """High-frequency API stress testing"""
    wait_time = between(0.1, 0.5)
    host = "http://localhost:8000"

    @task(20)
    def list_templates(self):
        page = random.randint(1, 5)
        self.client.get(f"/api/v1/templates?page={page}&page_size=20")

    @task(10)
    def get_featured(self):
        self.client.get("/api/v1/templates/featured?limit=10")

    @task(10)
    def get_popular(self):
        self.client.get("/api/v1/templates/popular?limit=10")

    @task(5)
    def search_templates(self):
        query = random.choice(["retail", "steady", "seasonal", "jit", "manufacturing"])
        self.client.get(f"/api/v1/templates?query={query}")

    @task(3)
    def get_template_by_id(self):
        template_id = random.randint(1, 36)
        self.client.get(f"/api/v1/templates/{template_id}")


class ConcurrentGameUser(HttpUser):
    """Simulate concurrent game operations"""
    wait_time = between(2, 5)
    host = "http://localhost:8000"

    def on_start(self):
        """Login"""
        response = self.client.post("/api/v1/auth/login", data={
            "username": "systemadmin@autonomy.ai",
            "password": "Autonomy@2025"
        })
        if response.status_code == 200:
            self.token = response.json().get("access_token")

    @task(5)
    def list_games(self):
        """List games"""
        self.client.get("/api/v1/games")

    @task(3)
    def list_supply_chains(self):
        """List supply chain configs"""
        self.client.get("/api/v1/supply-chain-configs")

    @task(2)
    def view_analytics(self):
        """View analytics dashboard data"""
        # Simulate analytics queries
        pass


# Locust command examples:
#
# Basic load test (100 users, 10 users/sec spawn rate):
# locust -f locustfile.py --users 100 --spawn-rate 10 --host http://localhost:8000
#
# Web UI mode:
# locust -f locustfile.py --host http://localhost:8000
# Then open http://localhost:8089
#
# Headless mode with specific duration:
# locust -f locustfile.py --users 100 --spawn-rate 10 --run-time 5m --headless --host http://localhost:8000
#
# Multiple user types:
# locust -f locustfile.py --users 100 --spawn-rate 10 TemplateUser:50 HealthCheckUser:30 APIStressUser:20
