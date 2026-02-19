"""
Environment-Specific Configuration
Phase 6 Sprint 5: Production Deployment & Testing

Manages environment-specific settings for dev, staging, and production.
"""

from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, validator


class Environment(str, Enum):
    """Environment types"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class ResourceLimits(BaseModel):
    """Resource limit configuration"""
    max_memory_mb: int = Field(default=2048, description="Maximum memory in MB")
    max_cpu_percent: float = Field(default=80.0, description="Maximum CPU usage %")
    max_db_connections: int = Field(default=20, description="Maximum database connections")
    max_concurrent_requests: int = Field(default=100, description="Maximum concurrent requests")
    request_timeout_seconds: int = Field(default=30, description="Request timeout in seconds")


class RateLimitConfig(BaseModel):
    """Rate limiting configuration"""
    enabled: bool = Field(default=True, description="Enable rate limiting")
    requests_per_minute: int = Field(default=60, description="Requests per minute per IP")
    requests_per_hour: int = Field(default=1000, description="Requests per hour per IP")
    burst_size: int = Field(default=10, description="Burst allowance")


class LoggingConfig(BaseModel):
    """Logging configuration"""
    level: str = Field(default="INFO", description="Log level")
    structured: bool = Field(default=True, description="Use structured JSON logging")
    log_queries: bool = Field(default=False, description="Log database queries")
    log_requests: bool = Field(default=True, description="Log HTTP requests")
    correlation_id_header: str = Field(default="X-Correlation-ID")


class SecurityConfig(BaseModel):
    """Security configuration"""
    cors_origins: list[str] = Field(default=["http://localhost:3000"])
    allowed_hosts: list[str] = Field(default=["*"])
    csrf_enabled: bool = Field(default=True, description="Enable CSRF protection")
    rate_limiting_enabled: bool = Field(default=True, description="Enable rate limiting")
    require_https: bool = Field(default=False, description="Require HTTPS")
    hsts_enabled: bool = Field(default=False, description="Enable HSTS header")
    max_upload_size_mb: int = Field(default=10, description="Maximum upload size in MB")


class CacheConfig(BaseModel):
    """Caching configuration"""
    enabled: bool = Field(default=False, description="Enable caching")
    backend: str = Field(default="memory", description="Cache backend (memory, redis)")
    ttl_seconds: int = Field(default=300, description="Default TTL in seconds")
    max_size: int = Field(default=1000, description="Maximum cache entries")


class MonitoringConfig(BaseModel):
    """Monitoring configuration"""
    metrics_enabled: bool = Field(default=True, description="Enable metrics collection")
    health_check_interval: int = Field(default=30, description="Health check interval in seconds")
    log_slow_queries: bool = Field(default=True, description="Log slow database queries")
    slow_query_threshold_ms: int = Field(default=1000, description="Slow query threshold in ms")


class EnvironmentConfig(BaseModel):
    """Complete environment configuration"""
    environment: Environment
    debug: bool = Field(default=False)
    testing: bool = Field(default=False)

    # Component configs
    resources: ResourceLimits = Field(default_factory=ResourceLimits)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)

    @validator("environment", pre=True)
    def validate_environment(cls, v):
        """Validate environment value"""
        if isinstance(v, str):
            try:
                return Environment(v.lower())
            except ValueError:
                raise ValueError(f"Invalid environment: {v}")
        return v


# Development configuration
DEVELOPMENT_CONFIG = EnvironmentConfig(
    environment=Environment.DEVELOPMENT,
    debug=True,
    testing=False,
    resources=ResourceLimits(
        max_memory_mb=4096,
        max_cpu_percent=90.0,
        max_db_connections=10,
        max_concurrent_requests=50,
        request_timeout_seconds=60
    ),
    rate_limit=RateLimitConfig(
        enabled=False,  # Disabled for development
        requests_per_minute=1000,
        requests_per_hour=10000
    ),
    logging=LoggingConfig(
        level="DEBUG",
        structured=False,
        log_queries=True,
        log_requests=True
    ),
    security=SecurityConfig(
        cors_origins=["http://localhost:3000", "http://localhost:8088"],
        allowed_hosts=["*"],
        csrf_enabled=False,
        rate_limiting_enabled=False,
        require_https=False,
        hsts_enabled=False,
        max_upload_size_mb=50
    ),
    cache=CacheConfig(
        enabled=False
    ),
    monitoring=MonitoringConfig(
        metrics_enabled=True,
        health_check_interval=60,
        log_slow_queries=True,
        slow_query_threshold_ms=500
    )
)


# Staging configuration
STAGING_CONFIG = EnvironmentConfig(
    environment=Environment.STAGING,
    debug=False,
    testing=False,
    resources=ResourceLimits(
        max_memory_mb=4096,
        max_cpu_percent=85.0,
        max_db_connections=30,
        max_concurrent_requests=100,
        request_timeout_seconds=30
    ),
    rate_limit=RateLimitConfig(
        enabled=True,
        requests_per_minute=120,
        requests_per_hour=2000,
        burst_size=20
    ),
    logging=LoggingConfig(
        level="INFO",
        structured=True,
        log_queries=False,
        log_requests=True
    ),
    security=SecurityConfig(
        cors_origins=[
            "https://staging.autonomy.ai",
            "https://staging-admin.autonomy.ai"
        ],
        allowed_hosts=["staging.autonomy.ai"],
        csrf_enabled=True,
        rate_limiting_enabled=True,
        require_https=True,
        hsts_enabled=True,
        max_upload_size_mb=10
    ),
    cache=CacheConfig(
        enabled=True,
        backend="memory",
        ttl_seconds=300,
        max_size=2000
    ),
    monitoring=MonitoringConfig(
        metrics_enabled=True,
        health_check_interval=30,
        log_slow_queries=True,
        slow_query_threshold_ms=1000
    )
)


# Production configuration
PRODUCTION_CONFIG = EnvironmentConfig(
    environment=Environment.PRODUCTION,
    debug=False,
    testing=False,
    resources=ResourceLimits(
        max_memory_mb=8192,
        max_cpu_percent=80.0,
        max_db_connections=50,
        max_concurrent_requests=200,
        request_timeout_seconds=30
    ),
    rate_limit=RateLimitConfig(
        enabled=True,
        requests_per_minute=60,
        requests_per_hour=1000,
        burst_size=10
    ),
    logging=LoggingConfig(
        level="INFO",
        structured=True,
        log_queries=False,
        log_requests=True
    ),
    security=SecurityConfig(
        cors_origins=[
            "https://autonomy.ai",
            "https://admin.autonomy.ai"
        ],
        allowed_hosts=["autonomy.ai"],
        csrf_enabled=True,
        rate_limiting_enabled=True,
        require_https=True,
        hsts_enabled=True,
        max_upload_size_mb=10
    ),
    cache=CacheConfig(
        enabled=True,
        backend="redis",
        ttl_seconds=600,
        max_size=5000
    ),
    monitoring=MonitoringConfig(
        metrics_enabled=True,
        health_check_interval=30,
        log_slow_queries=True,
        slow_query_threshold_ms=2000
    )
)


# Test configuration
TEST_CONFIG = EnvironmentConfig(
    environment=Environment.TEST,
    debug=True,
    testing=True,
    resources=ResourceLimits(
        max_memory_mb=1024,
        max_cpu_percent=95.0,
        max_db_connections=5,
        max_concurrent_requests=20,
        request_timeout_seconds=10
    ),
    rate_limit=RateLimitConfig(
        enabled=False
    ),
    logging=LoggingConfig(
        level="WARNING",
        structured=False,
        log_queries=False,
        log_requests=False
    ),
    security=SecurityConfig(
        cors_origins=["*"],
        allowed_hosts=["*"],
        csrf_enabled=False,
        rate_limiting_enabled=False,
        require_https=False,
        hsts_enabled=False,
        max_upload_size_mb=1
    ),
    cache=CacheConfig(
        enabled=False
    ),
    monitoring=MonitoringConfig(
        metrics_enabled=False,
        health_check_interval=300,
        log_slow_queries=False
    )
)


def get_environment_config(env: str = "development") -> EnvironmentConfig:
    """
    Get configuration for specified environment.

    Args:
        env: Environment name (development, staging, production, test)

    Returns:
        EnvironmentConfig for the specified environment

    Raises:
        ValueError: If environment is invalid
    """
    env = env.lower()
    configs = {
        "development": DEVELOPMENT_CONFIG,
        "staging": STAGING_CONFIG,
        "production": PRODUCTION_CONFIG,
        "test": TEST_CONFIG
    }

    if env not in configs:
        raise ValueError(
            f"Invalid environment: {env}. "
            f"Must be one of: {', '.join(configs.keys())}"
        )

    return configs[env]


def get_current_environment() -> Environment:
    """
    Get current environment from settings.

    Returns:
        Current Environment enum value
    """
    import os
    env_name = os.getenv("ENVIRONMENT", "development").lower()
    try:
        return Environment(env_name)
    except ValueError:
        return Environment.DEVELOPMENT
