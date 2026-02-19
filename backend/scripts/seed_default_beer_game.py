#!/usr/bin/env python3
"""Seed only the Default Beer Game group and related configs/games."""

from __future__ import annotations

from scripts.seed_default_group import (
    INVENTORY_CONFIG_NAME,
    build_seed_options_from_args,
    get_config_specs,
    parse_args,
    run_seed_with_session,
    session_factory_from_settings,
)

DEFAULT_BEER_GAME_CONFIG_NAMES = [
    INVENTORY_CONFIG_NAME,
    "Case Beer Game",
    "Six-Pack Beer Game",
    "Bottle Beer Game",
]


def main() -> None:
    args = parse_args()
    options = build_seed_options_from_args(args)
    config_specs = get_config_specs(DEFAULT_BEER_GAME_CONFIG_NAMES)
    session_factory = session_factory_from_settings()
    run_seed_with_session(
        session_factory,
        options,
        config_specs_override=config_specs,
        include_complex=True,
    )


if __name__ == "__main__":
    main()
