#!/usr/bin/env python
"""Backward-compatibility wrapper — delegates to check_llm_connection.py.

This script is kept for backward compatibility only.
Use ``check_llm_connection.py`` directly for provider-agnostic LLM checks.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

# Delegate to the provider-agnostic script in the same directory.
_NEW_SCRIPT = Path(__file__).with_name("check_llm_connection.py")
sys.argv[0] = str(_NEW_SCRIPT)
runpy.run_path(str(_NEW_SCRIPT), run_name="__main__")
