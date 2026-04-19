#!/usr/bin/env python3
"""
Generate all 11 TMS TRM training corpora in one invocation.

Usage:
    python scripts/pretraining/generate_all_tms_trms.py
    python scripts/pretraining/generate_all_tms_trms.py --samples 100000
    python scripts/pretraining/generate_all_tms_trms.py --output-dir /data/tms_corpus
"""
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.pretraining.generate_tms_corpus import main

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--all"] + sys.argv[1:]
    main()
