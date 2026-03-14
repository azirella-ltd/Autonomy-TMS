#!/usr/bin/env python3
"""F1: Hive Signal Bus & Urgency Vector Validation"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import importlib.util
import math
import threading
from datetime import datetime, timezone, timedelta

# Direct module load to avoid powell/__init__.py (which triggers DB config)
_POWELL_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'app', 'services', 'powell')

def _load_module(name, filepath):
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_hive = _load_module("hive_signal", os.path.join(_POWELL_DIR, "hive_signal.py"))

HiveSignalBus = _hive.HiveSignalBus
HiveSignal = _hive.HiveSignal
HiveSignalType = _hive.HiveSignalType
UrgencyVector = _hive.UrgencyVector
DECAY_THRESHOLD = _hive.DECAY_THRESHOLD
_LN2 = _hive._LN2

passed = 0
failed = 0
errors = []


def test(name, condition, detail=""):
    global passed, failed, errors
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        errors.append(f"{name}: {detail}")
        print(f"  FAIL: {name} -- {detail}")


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"F1: Hive Signal Bus & Urgency Vector Validation")
    print(f"{'='*60}")

    # ------------------------------------------------------------------
    # 1. Signal emission and read
    # ------------------------------------------------------------------
    print("\n--- 1. Signal emission and read ---")
    bus = HiveSignalBus()
    sig = HiveSignal(
        source_trm="po_creation",
        signal_type=HiveSignalType.PO_EXPEDITE,
        urgency=0.8,
        direction="shortage",
    )
    bus.emit(sig)
    test("Bus length after emit", len(bus) == 1, f"expected 1, got {len(bus)}")

    results = bus.read("atp_executor")
    test("Read returns emitted signal", len(results) == 1, f"expected 1, got {len(results)}")
    test(
        "Signal type matches",
        results[0].signal_type == HiveSignalType.PO_EXPEDITE,
        f"got {results[0].signal_type}",
    )

    # ------------------------------------------------------------------
    # 2. Exponential decay
    # ------------------------------------------------------------------
    print("\n--- 2. Exponential decay ---")
    half_life = 30.0
    now = datetime.now(timezone.utc)

    sig_t0 = HiveSignal(
        source_trm="atp_executor",
        signal_type=HiveSignalType.ATP_SHORTAGE,
        urgency=1.0,
        half_life_minutes=half_life,
        timestamp=now,
    )
    strength_t0 = sig_t0.current_strength
    test("Strength at t=0 ~ 1.0", abs(strength_t0 - 1.0) < 0.05, f"got {strength_t0:.4f}")

    sig_half = HiveSignal(
        source_trm="atp_executor",
        signal_type=HiveSignalType.ATP_SHORTAGE,
        urgency=1.0,
        half_life_minutes=half_life,
        timestamp=now - timedelta(minutes=half_life),
    )
    strength_half = sig_half.current_strength
    test(
        "Strength at t=half_life ~ 0.5",
        abs(strength_half - 0.5) < 0.05,
        f"expected ~0.5, got {strength_half:.4f}",
    )

    sig_2half = HiveSignal(
        source_trm="atp_executor",
        signal_type=HiveSignalType.ATP_SHORTAGE,
        urgency=1.0,
        half_life_minutes=half_life,
        timestamp=now - timedelta(minutes=2 * half_life),
    )
    strength_2half = sig_2half.current_strength
    test(
        "Strength at t=2*half_life ~ 0.25",
        abs(strength_2half - 0.25) < 0.05,
        f"expected ~0.25, got {strength_2half:.4f}",
    )

    # ------------------------------------------------------------------
    # 3. Ring buffer overflow
    # ------------------------------------------------------------------
    print("\n--- 3. Ring buffer overflow ---")
    bus2 = HiveSignalBus(max_signals=200)
    for i in range(250):
        bus2.emit(HiveSignal(
            source_trm="po_creation",
            signal_type=HiveSignalType.PO_EXPEDITE,
            urgency=0.5,
            payload={"seq": i},
        ))
    test("Ring buffer capped at max_signals", len(bus2) == 200, f"got {len(bus2)}")

    all_signals = bus2.read("atp_executor")
    seqs = [s.payload.get("seq") for s in all_signals]
    min_seq = min(seqs) if seqs else -1
    test(
        "Oldest signals evicted (min seq >= 50)",
        min_seq >= 50,
        f"min seq = {min_seq}",
    )

    # ------------------------------------------------------------------
    # 4. Self-signal exclusion
    # ------------------------------------------------------------------
    print("\n--- 4. Self-signal exclusion ---")
    bus3 = HiveSignalBus()
    bus3.emit(HiveSignal(
        source_trm="atp_executor",
        signal_type=HiveSignalType.ATP_SHORTAGE,
        urgency=0.9,
    ))
    bus3.emit(HiveSignal(
        source_trm="po_creation",
        signal_type=HiveSignalType.PO_EXPEDITE,
        urgency=0.7,
    ))

    own_results = bus3.read("atp_executor")
    own_sources = [s.source_trm for s in own_results]
    test(
        "Self-signal excluded from read",
        "atp_executor" not in own_sources,
        f"own signals found: {own_sources}",
    )
    test(
        "Other signals still visible",
        "po_creation" in own_sources,
        f"sources: {own_sources}",
    )

    # ------------------------------------------------------------------
    # 5. Urgency vector - set and read
    # ------------------------------------------------------------------
    print("\n--- 5. Urgency vector set and read ---")
    uv = UrgencyVector()
    trms_to_test = [
        ("atp_executor", 0.9, "shortage"),
        ("po_creation", 0.5, "surplus"),
        ("mo_execution", 0.3, "risk"),
        ("to_execution", 0.7, "relief"),
    ]
    for trm_name, urgency, direction in trms_to_test:
        uv.update(trm_name, urgency, direction)

    for trm_name, expected_urg, expected_dir in trms_to_test:
        val, dir_, _ = uv.read(trm_name)
        test(
            f"Urgency read {trm_name}",
            abs(val - expected_urg) < 1e-9 and dir_ == expected_dir,
            f"expected ({expected_urg}, {expected_dir}), got ({val}, {dir_})",
        )

    # ------------------------------------------------------------------
    # 6. Urgency clamping
    # ------------------------------------------------------------------
    print("\n--- 6. Urgency clamping ---")
    uv2 = UrgencyVector()
    uv2.update("atp_executor", 1.5, "shortage")
    val_high, _, _ = uv2.read("atp_executor")
    test("Urgency clamped to 1.0 (set 1.5)", val_high == 1.0, f"got {val_high}")

    uv2.update("atp_executor", -0.3, "surplus")
    val_low, _, _ = uv2.read("atp_executor")
    test("Urgency clamped to 0.0 (set -0.3)", val_low == 0.0, f"got {val_low}")

    uv2.update("po_creation", 0.9, "shortage")
    uv2.adjust("po_creation", 0.5)
    val_adj, _, _ = uv2.read("po_creation")
    test("Adjust clamped to 1.0 (0.9 + 0.5)", val_adj == 1.0, f"got {val_adj}")

    uv2.update("po_creation", 0.1, "surplus")
    uv2.adjust("po_creation", -0.5)
    val_adj2, _, _ = uv2.read("po_creation")
    test("Adjust clamped to 0.0 (0.1 - 0.5)", val_adj2 == 0.0, f"got {val_adj2}")

    # ------------------------------------------------------------------
    # 7. Thread safety - concurrent read/write
    # ------------------------------------------------------------------
    print("\n--- 7. Thread safety ---")
    bus4 = HiveSignalBus()
    thread_errors = []

    def writer():
        try:
            for i in range(100):
                bus4.emit(HiveSignal(
                    source_trm="po_creation",
                    signal_type=HiveSignalType.PO_EXPEDITE,
                    urgency=0.5,
                ))
                bus4.urgency.update("po_creation", i / 100.0, "shortage")
        except Exception as e:
            thread_errors.append(f"writer: {e}")

    def reader():
        try:
            for i in range(100):
                bus4.read("atp_executor")
                bus4.urgency.read("po_creation")
                bus4.urgency.snapshot()
        except Exception as e:
            thread_errors.append(f"reader: {e}")

    threads = [
        threading.Thread(target=writer),
        threading.Thread(target=reader),
        threading.Thread(target=writer),
        threading.Thread(target=reader),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    test(
        "Concurrent read/write no crashes",
        len(thread_errors) == 0,
        f"errors: {thread_errors}",
    )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)
