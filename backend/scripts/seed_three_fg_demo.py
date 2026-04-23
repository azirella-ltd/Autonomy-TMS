#!/usr/bin/env python3
"""Seed only the Three FG demo tenant and its scenarios."""

from __future__ import annotations

from scripts.seed_default_tenant import (
    build_seed_options_from_args,
    get_config_specs,
    parse_args,
    run_seed_with_session,
    session_factory_from_settings,
)

THREE_FG_CONFIG_NAMES = ["Three FG Beer Scenario"]


def main() -> None:
    args = parse_args()
    options = build_seed_options_from_args(args)
    config_specs = get_config_specs(THREE_FG_CONFIG_NAMES)
    session_factory = session_factory_from_settings()
    run_seed_with_session(
        session_factory,
        options,
        config_specs_override=config_specs,
        include_complex=False,
    )


if __name__ == "__main__":
    main()
