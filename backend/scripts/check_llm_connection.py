#!/usr/bin/env python
"""CLI utility to verify LLM provider connectivity.

Supports any OpenAI-compatible API: vLLM, Ollama, DeepSeek, LiteLLM, etc.

This script loads environment variables (optionally from a given .env file)
and calls :func:`check_autonomy_llm_access` to ensure the configured
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
        description="Probe the configured LLM provider (vLLM, Ollama, or OpenAI-compatible).",
    )
    parser.add_argument(
        "--model",
        help=(
            "Override the model identifier to probe. "
            "Defaults to LLM_MODEL_NAME or AUTONOMY_LLM_MODEL env, then qwen3-8b."
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

    # Legacy alias: GPT_ID -> AUTONOMY_LLM_MODEL
    if "AUTONOMY_LLM_MODEL" not in os.environ and "GPT_ID" in os.environ:
        os.environ.setdefault("AUTONOMY_LLM_MODEL", os.environ["GPT_ID"])


def resolve_probe():
    """Attempt to import the Autonomy connectivity probe."""

    try:
        module = importlib.import_module("app.services.llm_agent")
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on local env
        return None, exc

    try:
        return module.check_autonomy_llm_access, None
    except AttributeError:  # pragma: no cover - defensive
        return None, AttributeError(
            "app.services.llm_agent.check_autonomy_llm_access is unavailable"
        )


def main() -> int:
    args = parse_args()

    try:
        load_environment(args.env_file)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    probe, import_error = resolve_probe()
    if probe is None:
        print("Unable to import the Autonomy LLM probe")
        if isinstance(import_error, ModuleNotFoundError):
            missing = import_error.name or str(import_error)
            print(
                "Missing dependency:",
                missing,
            )
            print(
                "Hint: install backend requirements with "
                "`pip install -r backend/requirements.txt`."
            )
        else:  # pragma: no cover - defensive
            print(import_error)
        return 3

    ok, detail = probe(model=args.model)

    if ok:
        print(f"Connection successful | model={detail}")
        return 0

    print("Connection failed")
    print(f"Reason: {detail}")
    missing = [
        var for var in ("LLM_API_BASE", "LLM_API_KEY")
        if not os.getenv(var)
    ]
    if missing:
        print(f"Hint: set one of these environment variables -> {', '.join(missing)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
