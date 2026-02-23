#!/usr/bin/env python
"""CLI utility to verify OpenAI Autonomy strategist connectivity.

This script loads environment variables (optionally from a given .env file)
so it can reuse the credentials you already configured for the Beer Game.
It then calls :func:`check_autonomy_llm_access` to ensure the configured
model can be reached.  A non-zero exit status indicates a failure.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure the backend package is on the Python path before importing internal modules.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe the Autonomy/OpenAI strategist using the configured credentials.",
    )
    parser.add_argument(
        "--model",
        help=(
            "Override the model identifier to probe (e.g. gpt-5-mini or your g-... custom GPT). "
            "Defaults to LLM_MODEL_NAME, then qwen3-8b."
        ),
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Optional path to a .env file to load before probing (defaults to auto-discovery).",
    )
    return parser.parse_args()


def load_environment(env_file: Path | None) -> None:
    if env_file is not None:
        if not env_file.exists():
            raise FileNotFoundError(f"Cannot find .env file at {env_file}")
        load_dotenv(env_file)
    else:
        # Load from the repository root if a .env is present.
        default_env = Path(__file__).resolve().parents[2] / ".env"
        load_dotenv(default_env, override=False)
        # Fall back to standard dotenv search if needed.
        load_dotenv(override=False)

