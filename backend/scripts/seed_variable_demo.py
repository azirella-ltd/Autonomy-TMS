#!/usr/bin/env python3
"""Seed only the Variable Beer Game group and its games."""

from __future__ import annotations

from scripts.seed_default_group import (
    VARIABLE_BEER_GAME_GROUP_NAME,
    build_seed_options_from_args,
    get_config_specs,
    parse_args,
    run_seed_with_session,
    session_factory_from_settings,
)

VARIABLE_BEER_GAME_CONFIG_NAMES = [VARIABLE_BEER_GAME_GROUP_NAME]


def main() -> None:
    args = parse_args()
    options = build_seed_options_from_args(args)
    config_specs = get_config_specs(VARIABLE_BEER_GAME_CONFIG_NAMES)
    session_factory = session_factory_from_settings()
    run_seed_with_session(
        session_factory,
        options,
        config_specs_override=config_specs,
        include_complex=False,
    )


if __name__ == "__main__":
    main()
