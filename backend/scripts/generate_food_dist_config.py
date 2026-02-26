#!/usr/bin/env python3
"""
Script to generate the Food Dist supply chain configuration.

This creates a learning customer with a realistic foodservice distribution
network modeled after Food Dist.

Usage:
    cd backend
    python scripts/generate_food_dist_config.py

Or with custom parameters:
    python scripts/generate_food_dist_config.py --tenant-name "Food Dist Demo" --admin-email "admin@example.com"
"""

import asyncio
import argparse
import logging
import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.db_urls import resolve_async_database_url
from app.services.food_dist_config_generator import generate_food_dist_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main(args):
    """Main entry point."""
    # Create database engine
    async_db_url = resolve_async_database_url()
    engine = create_async_engine(
        async_db_url,
        echo=args.verbose,
    )

    # Create session factory
    async_session = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    logger.info("=" * 60)
    logger.info("Food Dist Configuration Generator")
    logger.info("=" * 60)
    logger.info(f"Tenant Name: {args.tenant_name}")
    logger.info(f"Admin Email: {args.admin_email}")
    logger.info(f"Admin Name: {args.admin_name}")
    logger.info("=" * 60)

    async with async_session() as session:
        try:
            result = await generate_food_dist_config(
                db=session,
                tenant_name=args.tenant_name,
                admin_email=args.admin_email,
                admin_name=args.admin_name,
            )

            logger.info("\n" + "=" * 60)
            logger.info("Generation Complete!")
            logger.info("=" * 60)
            logger.info(f"Customer ID: {result['customer_id']}")
            logger.info(f"Config ID: {result['config_id']}")
            logger.info(f"Admin User ID: {result['admin_user_id']}")
            logger.info("-" * 40)
            logger.info(f"Suppliers Created: {result['suppliers_created']}")
            logger.info(f"Customers Created: {result['customers_created']}")
            logger.info(f"Products Created: {result['products_created']}")
            logger.info(f"Lanes Created: {result['lanes_created']}")
            logger.info(f"Vendor Products: {result['vendor_products_created']}")
            logger.info(f"Forecasts Created: {result['forecasts_created']}")
            logger.info(f"Policies Created: {result['policies_created']}")
            logger.info("-" * 40)
            logger.info("Summary:")
            for key, value in result['summary'].items():
                logger.info(f"  {key}: {value}")
            logger.info("=" * 60)

            logger.info("\nTo login, use:")
            logger.info(f"  Email: {args.admin_email}")
            logger.info("  Password: Autonomy@2025")

        except Exception as e:
            logger.error(f"Generation failed: {e}")
            await session.rollback()
            raise

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate Food Dist supply chain configuration"
    )
    parser.add_argument(
        "--tenant-name",
        default="Food Dist",
        help="Name of the learning tenant (default: Food Dist)"
    )
    parser.add_argument(
        "--admin-email",
        default="admin@distdemo.com",
        help="Email for the tenant admin (default: admin@distdemo.com)"
    )
    parser.add_argument(
        "--admin-name",
        default="Food Dist Admin",
        help="Name for the tenant admin (default: Food Dist Admin)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose SQL logging"
    )

    args = parser.parse_args()
    asyncio.run(main(args))
