#!/usr/bin/env python3
"""
One-time bulk index: embed all existing SC configs into tenant knowledge bases.

Run inside the backend container:
    docker compose exec backend python scripts/index_all_configs.py
"""

import asyncio
import logging
import sys

# Ensure app is importable
sys.path.insert(0, "/app")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("index_all_configs")


async def main():
    from app.db.kb_session import get_kb_session, init_kb_engine
    from app.db.session import sync_session_factory
    from app.models.supply_chain_config import SupplyChainConfig
    from app.services.sc_config_indexer import ScConfigIndexer

    # Initialize KB engine
    init_kb_engine()

    # Get all configs using sync session (config tables are in main DB)
    db = sync_session_factory()
    try:
        configs = db.query(SupplyChainConfig).all()
        logger.info(f"Found {len(configs)} supply chain configs to index")

        if not configs:
            logger.info("No configs found. Nothing to index.")
            return

        # Group by tenant
        tenant_configs = {}
        for cfg in configs:
            tenant_id = cfg.tenant_id
            tenant_configs.setdefault(tenant_id, []).append(
                {"id": cfg.id, "name": cfg.name, "tenant_id": cfg.tenant_id}
            )

        logger.info(f"Across {len(tenant_configs)} tenant(s)")
    finally:
        db.close()

    # Index each tenant's configs via async KB session
    total_indexed = 0
    total_errors = 0

    for tenant_id, cfgs in tenant_configs.items():
        logger.info(f"\n--- Tenant {tenant_id}: {len(cfgs)} config(s) ---")

        for cfg_info in cfgs:
            try:
                async with get_kb_session() as kb_db:
                    indexer = ScConfigIndexer(kb_db=kb_db, tenant_id=tenant_id)
                    result = await indexer.index_config(cfg_info["id"])
                    status = result.get("status", "ok")
                    chunks = result.get("chunk_count", 0)
                    logger.info(
                        f"  Config '{cfg_info['name']}' (id={cfg_info['id']}): "
                        f"status={status}, chunks={chunks}"
                    )
                    total_indexed += 1
            except Exception as e:
                logger.error(f"  Config '{cfg_info['name']}' (id={cfg_info['id']}): FAILED — {e}")
                total_errors += 1

    logger.info(f"\n=== Done: {total_indexed} indexed, {total_errors} errors ===")


if __name__ == "__main__":
    asyncio.run(main())
