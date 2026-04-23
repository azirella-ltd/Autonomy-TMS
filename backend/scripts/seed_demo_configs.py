#!/usr/bin/env python3
"""Seed only the default demo tenant and related configs/scenarios."""

from __future__ import annotations

from scripts.seed_default_tenant import (
    INVENTORY_CONFIG_NAME,
    build_seed_options_from_args,
    get_config_specs,
    parse_args,
    run_seed_with_session,
    session_factory_from_settings,
)

DEFAULT_CONFIG_NAMES = [
    INVENTORY_CONFIG_NAME,
    "Case Beer Scenario",
    "Six-Pack Beer Scenario",
    "Bottle Beer Scenario",
]


def main() -> None:
    args = parse_args()
    options = build_seed_options_from_args(args)
    config_specs = get_config_specs(DEFAULT_CONFIG_NAMES)
    session_factory = session_factory_from_settings()
    run_seed_with_session(
        session_factory,
        options,
        config_specs_override=config_specs,
        include_complex=True,
    )


if __name__ == "__main__":
    main()
