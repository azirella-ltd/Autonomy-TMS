#!/usr/bin/env python3
"""End-to-end bootstrap for the Autonomy supply chain system."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

# Allow imports from the backend package when running as a script
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.append(str(BACKEND_ROOT))

REPO_ROOT = BACKEND_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from sqlalchemy.orm import sessionmaker

from app.db.init_db import init_db
from app.db.session import sync_engine
from app.services.llm_agent import check_autonomy_llm_access
from scripts.seed_default_tenant import (
    SeedOptions,
    run_seed_with_session,
)

logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)


def _session_factory() -> sessionmaker:
    if sync_engine is None:
        raise RuntimeError("Synchronous database engine is not configured.")
    return sessionmaker(bind=sync_engine, autocommit=False, autoflush=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-training",
        action="store_true",
        help="Skip synthetic dataset generation and temporal GNN training.",
    )
    parser.add_argument(
        "--skip-autonomy-games",
        action="store_true",
        help="Do not create or update the showcase Autonomy games.",
    )
    parser.add_argument(
        action="store_true",
        help="Preserve existing games instead of rebuilding them from scratch.",
    )
    parser.add_argument(
        "--agent-strategy",
        default=None,
        help="Override the default AI agent strategy (e.g. llm, pid_heuristic, naive).",
    )
    parser.add_argument(
        "--llm-model",
        default=None,
        help="LLM model identifier to use when the agent strategy is 'llm'.",
    )
    parser.add_argument(
        "--llm-timeout",
        type=float,
        default=5.0,
        help="Timeout in seconds for the Autonomy LLM availability probe.",
    )
    return parser.parse_args()


def bootstrap_system(args: argparse.Namespace) -> None:
    logger.info("[1/4] Initialising database schema...")
    asyncio.run(init_db())
    logger.info("Database initialisation complete.")

    preferred_strategy: Optional[str]
    if args.agent_strategy:
        logger.info("Agent strategy override requested: %s", args.agent_strategy)
        llm_available = None
        preferred_strategy = args.agent_strategy
    else:
        llm_available, llm_detail = check_autonomy_llm_access(
            model=args.llm_model,
            request_timeout=args.llm_timeout,
        )
        if llm_available:
            logger.info(
                "Autonomy LLM probe succeeded; default AI scenario_users will use the LLM strategy (%s).",
                args.llm_model or "auto",
            )
        else:
            logger.warning(
                "Autonomy LLM probe failed (%s); falling back to PID heuristic agents.",
                llm_detail,
            )
        preferred_strategy = "llm" if llm_available else "pid_heuristic"

    factory = _session_factory()

    seed_options = SeedOptions(
        reset_games=not args.no_reset_games,
        force_dataset=not args.skip_training,
        force_training=not args.skip_training,
        create_autonomy_games=not args.skip_autonomy_games,
        assign_ai_agents=True,
        preferred_agent_strategy=preferred_strategy,
        preferred_llm_model=args.llm_model,
    )

    logger.info("[2/4] Seeding default users, groups, and games...")
    run_seed_with_session(factory, seed_options)
    logger.info("Seed workflow complete.")

    if args.skip_training:
        logger.info("Training skipped as requested; no dataset or GNN model was regenerated.")
    else:
        logger.info("Dataset generation and GNN training executed via seeding pipeline.")

    logger.info("[3/4] Verifying Autonomy Autonomy agent configuration...")
    if args.agent_strategy:
        logger.info("Default AI agents configured with explicit strategy '%s'.", args.agent_strategy)
    elif llm_available:
        logger.info("Default AI agents configured to use the Autonomy LLM strategy.")
    else:
        logger.info("Default AI agents configured to use the PID heuristic strategy.")

    logger.info("[4/4] Bootstrap completed successfully.")


def main() -> None:
    args = parse_args()
    bootstrap_system(args)


if __name__ == "__main__":
    main()
