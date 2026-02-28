import os
import logging
import asyncio
from sqlalchemy import create_engine, exc, text, select, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import all models to ensure they are registered with SQLAlchemy
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Import models in the correct order to avoid circular imports
from app.models.base import Base
from app.models.compatibility import Item, ProductSiteConfig  # Temporary compat
from app.models.user import User, RefreshToken, UserTypeEnum
from app.models.participant import ScenarioUser, ScenarioUserRole, ScenarioUserType, ScenarioUserStrategy
from app.models.auth_models import PasswordHistory, PasswordResetToken
from app.models.session import TokenBlacklist, UserSession
from app.models.scenario import Scenario, ScenarioStatus, Round, ScenarioUserAction
from app.models.tenant import Tenant, TenantMode
from app.models.supply_chain_config import SupplyChainConfig, Node, Lane, Market, MarketDemand
from app.models.sc_entities import Product
from app.models.mps import MPSPlan, MPSPlanItem, MPSCapacityCheck
from app.models.sc_entities import (
    Forecast, SupplyPlan, ProductBom, ProductionProcess, SourcingRules,
    InvPolicy, OutboundOrderLine, InvLevel
)
from app.models.sc_planning import InboundOrderLine
from app.models.monte_carlo import (
    MonteCarloRun, MonteCarloScenario, MonteCarloTimeSeries, MonteCarloRiskAlert
)
try:
    from scripts.seed_core_config import seed_core_config
except ModuleNotFoundError:  # pragma: no cover - fallback when script package unavailable
    async def seed_core_config(*args, **kwargs):
        logger.warning(
            "seed_core_config module not found; continuing without core config seeding."
        )
from app.core.security import get_password_hash

# Ensure all models are imported and registered with SQLAlchemy
# This is necessary for proper relationship resolution
_models = [Tenant, User, RefreshToken, ScenarioUser, PasswordHistory, PasswordResetToken,
           TokenBlacklist, UserSession, Scenario, Round, ScenarioUserAction]

# Log model registration
logger.info(f"Registered models: {[model.__name__ for model in _models]}")

# Import settings and database URL resolvers
from app.core.config import settings
from app.core.db_urls import resolve_async_database_url, resolve_sync_database_url

# Create async database engine using centralized URL resolver
async_uri = resolve_async_database_url()
sync_uri = resolve_sync_database_url()

logger.info(f"Initializing database with async URL: {async_uri.split('@')[-1] if '@' in async_uri else async_uri}")

engine = create_async_engine(
    async_uri,
    echo=True
)

# Create async session factory
async_session_factory = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# Database creation is handled by Docker initialization scripts:
# - For PostgreSQL: init_db_postgres.sql
# - For MariaDB: init_db.sql
# No need for manual database creation here

async def init_db():
    """
    Initialize the database with required tables and initial data.
    """
    # Create all tables
    logger.info("Creating database tables...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create tables: {e}")
        import traceback
        traceback.print_exc()
        raise
    
    # Create a session to add initial data
    async with async_session_factory() as db:
        try:
            # Add any initial data here if needed
            logger.info("Adding initial data...")
            
            # Check if system administrator user already exists
            systemadmin_email = (
                os.getenv("SYSTEMADMIN_EMAIL")
                or os.getenv("SUPERADMIN_EMAIL")
                or "systemadmin@autonomy.ai"
            )
            systemadmin_password = (
                os.getenv("SYSTEMADMIN_PASSWORD")
                or os.getenv("SUPERADMIN_PASSWORD")
                or os.getenv("AUTONOMY_DEFAULT_PASSWORD")
                or "Autonomy@2026"
            )

            result = await db.execute(
                select(User).where(User.email == systemadmin_email)
            )
            systemadmin = result.scalars().first()

            if not systemadmin:
                logger.info("Creating system administrator user...")
                systemadmin = User(
                    username="systemadmin",
                    email=systemadmin_email,
                    hashed_password=get_password_hash(systemadmin_password),
                    is_superuser=True,
                    is_active=True,
                    user_type=UserTypeEnum.SYSTEM_ADMIN,
                )
                db.add(systemadmin)
                await db.commit()
                await db.refresh(systemadmin)
                logger.info("System administrator user created successfully")

            # Ensure default Autonomy tenant exists
            result = await db.execute(select(Tenant).where(Tenant.name == "Autonomy"))
            tenant = result.scalars().first()
            if not tenant:
                tenant = Tenant(
                    name="Autonomy", description="Default tenant", admin_id=systemadmin.id
                )
                db.add(tenant)
                await db.flush()

            # Assign tenant to system administrator and any users missing a tenant
            systemadmin.tenant_id = tenant.id
            await db.execute(
                update(User).where(User.tenant_id.is_(None)).values(tenant_id=tenant.id)
            )

            # Seed core supply chain configuration
            await seed_core_config(db)

            # Add other initial data as needed

            await db.commit()
            logger.info("Initial data added successfully")
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error initializing database: {e}")
            raise

async def async_main():
    await init_db()
    await engine.dispose()

if __name__ == "__main__":
    print("Initializing database...")
    asyncio.run(async_main())
    print("Database initialized successfully!")
