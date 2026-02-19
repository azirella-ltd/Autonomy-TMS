"""Seed default supply chain configuration and games during DB initialisation."""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

SEED_UTILS_AVAILABLE = True

try:  # pragma: no cover - heavy seed utilities already tested elsewhere
    from backend.scripts.seed_default_group import (
        DEFAULT_AGENT_TYPE,
        DEFAULT_CONFIG_NAME,
        DEFAULT_GAME_NAME,
        LOGNORMAL_CONFIG_DESCRIPTION,
        LOGNORMAL_CONFIG_NAME,
        LOGNORMAL_DEMAND_PATTERN,
        NAIVE_AGENT_GAME_NAME,
        ensure_ai_agents,
        ensure_autonomy_games,
        ensure_default_game,
        ensure_group,
        ensure_naive_unsupervised_game,
        ensure_role_users,
        ensure_supply_chain_config,
        resolve_default_agent_strategy,
        _configure_game_agents,
    )
except Exception as exc:  # pragma: no cover - import guard for optional dependency
    logger.warning("Unable to import seed_default_group helpers: %s", exc)
    DEFAULT_AGENT_TYPE = "pi_heuristic"
    SEED_UTILS_AVAILABLE = False

    def ensure_ai_agents(*args: Any, **kwargs: Any) -> None:  # type: ignore[misc]
        raise RuntimeError("seed_default_group utilities unavailable")

    def ensure_autonomy_games(*args: Any, **kwargs: Any) -> None:  # type: ignore[misc]
        raise RuntimeError("seed_default_group utilities unavailable")

    def ensure_default_game(*args: Any, **kwargs: Any) -> None:  # type: ignore[misc]
        raise RuntimeError("seed_default_group utilities unavailable")

    def ensure_group(*args: Any, **kwargs: Any) -> None:  # type: ignore[misc]
        raise RuntimeError("seed_default_group utilities unavailable")

    def ensure_naive_unsupervised_game(*args: Any, **kwargs: Any) -> None:  # type: ignore[misc]
        raise RuntimeError("seed_default_group utilities unavailable")

    def ensure_role_users(*args: Any, **kwargs: Any) -> None:  # type: ignore[misc]
        raise RuntimeError("seed_default_group utilities unavailable")

    def ensure_supply_chain_config(*args: Any, **kwargs: Any) -> None:  # type: ignore[misc]
        raise RuntimeError("seed_default_group utilities unavailable")

    def resolve_default_agent_strategy(*args: Any, **kwargs: Any):  # type: ignore[misc]
        return DEFAULT_AGENT_TYPE, None, None

    def _configure_game_agents(*args: Any, **kwargs: Any) -> None:  # type: ignore[misc]
        raise RuntimeError("seed_default_group utilities unavailable")


def _seed_with_sync_session(session: Session) -> None:
    """Populate default group, supply chain configuration, and showcase games."""

    if not SEED_UTILS_AVAILABLE:
        logger.warning(
            "Default seed utilities unavailable; skipping supply chain bootstrap."
        )
        return

    logger.info("Seeding default supply chain configuration and showcase games")

    group, _ = ensure_group(session)
    ensure_role_users(session, group)

    strategy, llm_model, probe_detail = resolve_default_agent_strategy(
        DEFAULT_AGENT_TYPE,
        None,
    )
    if probe_detail:
        logger.info("Autonomy LLM probe: %s", probe_detail)

    config_specs = [
        {
            "config_name": DEFAULT_CONFIG_NAME,
            "config_description": None,
            "demand_pattern": None,
            "game_name": DEFAULT_GAME_NAME,
            "naive_game_name": NAIVE_AGENT_GAME_NAME,
            "autonomy_suffix": None,
        },
        {
            "config_name": LOGNORMAL_CONFIG_NAME,
            "config_description": LOGNORMAL_CONFIG_DESCRIPTION,
            "demand_pattern": LOGNORMAL_DEMAND_PATTERN,
            "game_name": f"{DEFAULT_GAME_NAME} ({LOGNORMAL_CONFIG_NAME})",
            "naive_game_name": f"{NAIVE_AGENT_GAME_NAME} ({LOGNORMAL_CONFIG_NAME})",
            "autonomy_suffix": LOGNORMAL_CONFIG_NAME,
        },
    ]

    artifacts_stub = {"dataset": None, "model": None, "device": None}

    for spec in config_specs:
        config = ensure_supply_chain_config(
            session,
            group,
            name=spec["config_name"],
            description=spec["config_description"],
            demand_pattern_override=spec["demand_pattern"],
        )

        game = ensure_default_game(
            session,
            group,
            config_name=spec["config_name"],
            config_description=spec["config_description"],
            demand_pattern_override=spec["demand_pattern"],
            game_name=spec["game_name"],
        )

        ensure_ai_agents(
            session,
            game,
            strategy,
            llm_model,
            spec.get("llm_strategy"),
        )
        session.flush()

        naive_game = ensure_naive_unsupervised_game(
            session,
            group,
            config,
            demand_pattern_override=spec["demand_pattern"],
            game_name=spec["naive_game_name"],
        )
        _configure_game_agents(session, naive_game, "naive")

        ensure_autonomy_games(
            session,
            group,
            config,
            artifacts_stub,
            recreate=False,
            name_suffix=spec["autonomy_suffix"],
        )

    session.flush()
    session.commit()

    logger.info("Default supply chain data successfully seeded")


async def seed_core_config(db_session: Optional[Any] = None, *args: Any, **kwargs: Any) -> None:
    """Seed the default supply chain configuration using async or sync sessions."""

    session = db_session
    if isinstance(session, AsyncSession):
        await session.run_sync(_seed_with_sync_session)
        return

    if isinstance(session, Session):
        _seed_with_sync_session(session)
        return

    if session is None:
        logger.warning("seed_core_config called without a database session; skipping")
        return

    raise TypeError(f"Unsupported session type for seeding: {type(session)!r}")
