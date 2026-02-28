#!/usr/bin/env python3
"""
Script to set up the default environment with a tenant admin, default tenant,
supply chain configuration, and a scenario with AI scenario_users.
"""
import asyncio
import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add the backend directory to the Python path
sys.path.append(str(Path(__file__).parent.parent / 'backend'))

import asyncio
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add the backend directory to the Python path
sys.path.append(str(Path(__file__).parent.parent / 'backend'))

import asyncio
import sys
import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add the backend directory to the Python path
sys.path.append(str(Path(__file__).parent.parent / 'backend'))

from sqlalchemy import select, update, insert, delete, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import async_session_factory, engine, Base
from app.models.user import User, UserBase
from app.models.tenant import Tenant
from app.models.supply_chain_config import SupplyChainConfig, Node, Lane, MarketDemand, NodeType
from app.models.compatibility import Item
from app.models.sc_entities import InvPolicy as ProductSiteConfig
from app.models.scenario import Scenario, ScenarioStatus
from app.models.scenario_user import ScenarioUser, ScenarioUserRole
from app.core.security import get_password_hash
from datetime import datetime

# Configure logging
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure logging
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def create_default_environment():
    """Create the default environment with tenant admin, tenant, and scenario."""
    # Create all tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with async_session_factory() as db:
        try:
            # Check if tenant admin already exists
            result = await db.execute(
                select(User).where(User.email == "tenantadmin@autonomy.ai")
            )
            tenant_admin = result.scalars().first()

            if not tenant_admin:
                # Create tenant admin user
                tenant_admin = User(
                    username="tenantadmin",
                    email="tenantadmin@autonomy.ai",
                    hashed_password=get_password_hash(os.getenv("AUTONOMY_DEFAULT_PASSWORD", "Autonomy@2026")),
                    full_name="Tenant Admin",
                    is_superuser=False,
                    is_active=True
                )
                db.add(tenant_admin)
                await db.flush()  # Flush to get the ID
                logger.info("Created tenant admin user: tenantadmin@autonomy.ai / Autonomy@2026")
        
            # Check if default tenant exists
            result = await db.execute(
                select(Tenant).where(Tenant.name == "Default Simulation")
            )
            default_tenant = result.scalars().first()
            
            if not default_tenant:
                # Create default tenant
                default_tenant = Tenant(
                    name="Default Simulation",
                    description="Default Tenant for Autonomy",
                    admin_id=tenant_admin.id
                )
                db.add(default_tenant)
                await db.flush()  # Flush to get the ID
                logger.info(f"✅ Created default tenant: {default_tenant.name}")
                
                # Update tenant admin with tenant_id
                tenant_admin.tenant_id = default_tenant.id
                await db.flush()
                logger.info(f"Updated tenant admin with tenant_id: {tenant_admin.tenant_id}")
            
            # Check if default supply chain config exists
            result = await db.execute(
                select(SupplyChainConfig).where(SupplyChainConfig.name == "Default Simulation")
            )
            default_config = result.scalars().first()
            
            if not default_config:
                # Create default supply chain configuration
                default_config = SupplyChainConfig(
                    name="Default Simulation",
                    description="Default supply chain configuration",
                    tenant_id=default_tenant.id,
                    created_by=tenant_admin.id
                )
                db.add(default_config)
                await db.flush()
            
                # Create nodes
                nodes = [
                    {"name": "Market Supply", "node_type": NodeType.MARKET_SUPPLY, "position_x": -1, "position_y": 0, "role": None},
                    {"name": "Manufacturer", "node_type": NodeType.MANUFACTURER, "position_x": 0, "position_y": 0, "role": ScenarioUserRole.MANUFACTURER},
                    {"name": "Distributor", "node_type": NodeType.DISTRIBUTOR, "position_x": 1, "position_y": 0, "role": ScenarioUserRole.DISTRIBUTOR},
                    {"name": "Wholesaler", "node_type": NodeType.WHOLESALER, "position_x": 2, "position_y": 0, "role": ScenarioUserRole.WHOLESALER},
                    {"name": "Retailer", "node_type": NodeType.RETAILER, "position_x": 3, "position_y": 0, "role": ScenarioUserRole.RETAILER},
                    {"name": "Market Demand", "node_type": NodeType.MARKET_DEMAND, "position_x": 4, "position_y": 0, "role": None},
                ]
                
                node_objs = []
                for node_data in nodes:
                    node = Node(
                        name=node_data["name"],
                        node_type=node_data["node_type"],
                        position_x=node_data["position_x"],
                        position_y=node_data["position_y"],
                        config_id=default_config.id
                    )
                    db.add(node)
                    node_objs.append(node)
                
                await db.flush()
                
                # Create lanes between nodes
                for i in range(len(node_objs) - 1):
                    lane = Lane(
                        source_id=node_objs[i].id,
                        target_id=node_objs[i+1].id,
                        config_id=default_config.id,
                        lead_time=1,
                        service_level=0.95
                    )
                    db.add(lane)
                
                # Create default item
                item = Item(name="Standard Product", description="Standard supply chain product")
                db.add(item)
                await db.flush()
                
                # Create item-node configurations
                for node in node_objs:
                    if node.node_type in {NodeType.MARKET_SUPPLY, NodeType.MARKET_DEMAND}:
                        continue
                    inc = ProductSiteConfig(
                        item_id=item.id,
                        node_id=node.id,
                        config_id=default_config.id,
                        holding_cost=1.0,
                        backlog_cost=2.0,
                        initial_inventory=12,
                        order_up_to=30,
                        reorder_point=10
                    )
                    db.add(inc)
                
                # Create market demand
                market_demand = MarketDemand(
                    config_id=default_config.id,
                    item_id=item.id,
                    mean_demand=8,
                    std_demand=2,
                    pattern_type="NORMAL"
                )
                db.add(market_demand)
            
                logger.info(f"✅ Created default supply chain configuration: {default_config.name}")
            
            # Create AI users for each role
            ai_users = {}
            for role in ["retailer", "wholesaler", "distributor", "manufacturer"]:
                ai_user = User(
                    username=f"ai_{role}",
                    email=f"ai_{role}@autonomy.ai",
                    hashed_password=get_password_hash(os.getenv("AUTONOMY_DEFAULT_PASSWORD", "Autonomy@2026")),
                    full_name=f"AI {role.capitalize()}",
                    is_superuser=False,
                    is_active=True,
                    tenant_id=default_tenant.id  # Add AI users to the default tenant
                )
                db.add(ai_user)
                await db.flush()
                ai_users[role] = ai_user
                logger.info(f"✅ Created AI scenario_user: {ai_user.username}")
            
            # Check if default scenario exists
            result = await db.execute(
                select(Scenario).where(Scenario.name == "Default Simulation")
            )
            default_scenario = result.scalars().first()
            
            if not default_scenario:
                # Create default scenario
                default_scenario = Scenario(
                    name="Default Simulation",
                    description="Default simulation with AI scenario_users",
                    max_rounds=50,
                    current_round=0,
                    status=ScenarioStatus.CREATED,
                    supply_chain_config_id=default_config.id,
                    tenant_id=default_tenant.id,
                    created_by=tenant_admin.id
                )
                db.add(default_scenario)
                await db.flush()
                
                # Create scenario_users for the scenario
                for role, user in ai_users.items():
                    scenario_user = ScenarioUser(
                        scenario_id=default_scenario.id,
                        user_id=user.id,
                        role=ScenarioUserRole[role.upper()],
                        is_ai=True,
                        strategy="naive"  # Simple ordering strategy
                    )
                    db.add(scenario_user)
                
                logger.info(f"✅ Created default scenario: {default_scenario.name}")
            
            # Commit all changes at the end
            await db.commit()
            logger.info("✅ Successfully set up default environment")

        except Exception as e:
            await db.rollback()
            logger.error(f"❌ Error setting up default environment: {e}")
            raise

if __name__ == "__main__":
    import asyncio
    
    logger.info("\n[+] Setting up default environment...")
    try:
        asyncio.run(create_default_environment())
    except Exception as e:
        logger.error(f"Failed to set up default environment: {e}")
        sys.exit(1)
