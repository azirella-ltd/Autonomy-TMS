#!/usr/bin/env python3
"""F7: TRM Checkpoint Save/Load Lifecycle Validation"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Set minimum env vars for app imports (DB not actually used)
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://x:x@localhost:5432/x")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import tempfile
import shutil
from datetime import date, datetime, timedelta

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
    print(f"F7: TRM Checkpoint Save/Load Lifecycle Validation")
    print(f"{'='*60}")

    try:
        import torch
        import torch.nn as nn
        HAS_TORCH = True
    except ImportError:
        HAS_TORCH = False
        print("  SKIP: PyTorch not available, skipping checkpoint tests")
        sys.exit(0)

    # Create a temp directory for checkpoints
    tmp_dir = tempfile.mkdtemp(prefix="trm_ckpt_test_")

    try:
        # ── Create a simple mock TRM model ────────────────────────────
        class MockTRM(nn.Module):
            def __init__(self, state_dim=16):
                super().__init__()
                self.fc1 = nn.Linear(state_dim, 32)
                self.fc2 = nn.Linear(32, 1)

            def forward(self, x):
                return self.fc2(torch.relu(self.fc1(x)))

        model = MockTRM(state_dim=16)
        # Initialize with specific weights for reproducibility
        with torch.no_grad():
            for p in model.parameters():
                p.fill_(0.42)

        # ── Test 1: Save checkpoint ───────────────────────────────────
        print("\n[Test 1] Save checkpoint")
        ckpt_path = os.path.join(tmp_dir, "trm_test_v1.pt")
        meta = {
            "model_state_dict": model.state_dict(),
            "trm_type": "atp_executor",
            "site_id": 42,
            "site_name": "TEST_SITE",
            "state_dim": 16,
            "model_class": "MockTRM",
            "config_id": 22,
            "version": 1,
            "saved_at": datetime.utcnow().isoformat(),
            "phase": "bc",
            "epoch": 50,
            "loss": 0.0123,
        }
        torch.save(meta, ckpt_path)
        test(
            "Checkpoint saved successfully",
            True,
            "",
        )

        # ── Test 2: Checkpoint file exists on disk ────────────────────
        print("\n[Test 2] Checkpoint file exists on disk")
        test(
            "Checkpoint file exists",
            os.path.exists(ckpt_path),
            f"Path: {ckpt_path}",
        )
        file_size = os.path.getsize(ckpt_path)
        test(
            "Checkpoint file is non-empty",
            file_size > 0,
            f"Size: {file_size} bytes",
        )

        # ── Test 3: Load checkpoint into fresh model ──────────────────
        print("\n[Test 3] Load checkpoint into fresh model")
        loaded_ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        fresh_model = MockTRM(state_dim=16)
        # Before loading, weights should be random (different from saved)
        fresh_model.load_state_dict(loaded_ckpt["model_state_dict"])

        # Verify state_dicts match
        original_sd = model.state_dict()
        loaded_sd = fresh_model.state_dict()
        all_match = True
        for key in original_sd:
            if key not in loaded_sd:
                all_match = False
                break
            if not torch.equal(original_sd[key], loaded_sd[key]):
                all_match = False
                break
        test(
            "Loaded state_dict matches original",
            all_match,
            "State dict mismatch detected",
        )

        # Verify outputs match
        test_input = torch.randn(1, 16)
        with torch.no_grad():
            original_out = model(test_input)
            loaded_out = fresh_model(test_input)
        test(
            "Loaded model produces same output as original",
            torch.allclose(original_out, loaded_out, atol=1e-6),
            f"Original: {original_out.item():.6f}, Loaded: {loaded_out.item():.6f}",
        )

        # ── Test 4: Checkpoint metadata persists ──────────────────────
        print("\n[Test 4] Checkpoint metadata (phase, epoch, loss) persists")
        test(
            "trm_type metadata persists",
            loaded_ckpt["trm_type"] == "atp_executor",
            f"Got {loaded_ckpt.get('trm_type')}",
        )
        test(
            "phase metadata persists",
            loaded_ckpt["phase"] == "bc",
            f"Got {loaded_ckpt.get('phase')}",
        )
        test(
            "epoch metadata persists",
            loaded_ckpt["epoch"] == 50,
            f"Got {loaded_ckpt.get('epoch')}",
        )
        test(
            "loss metadata persists",
            abs(loaded_ckpt["loss"] - 0.0123) < 1e-6,
            f"Got {loaded_ckpt.get('loss')}",
        )
        test(
            "site_id metadata persists",
            loaded_ckpt["site_id"] == 42,
            f"Got {loaded_ckpt.get('site_id')}",
        )
        test(
            "version metadata persists",
            loaded_ckpt["version"] == 1,
            f"Got {loaded_ckpt.get('version')}",
        )

        # ── Test 5: Loading nonexistent checkpoint ────────────────────
        print("\n[Test 5] Loading nonexistent checkpoint")
        nonexistent_path = os.path.join(tmp_dir, "does_not_exist.pt")
        load_error = None
        try:
            torch.load(nonexistent_path, map_location="cpu", weights_only=False)
        except (FileNotFoundError, Exception) as e:
            load_error = e
        test(
            "Loading nonexistent checkpoint raises error",
            load_error is not None,
            "No error was raised",
        )
        test(
            "Error is FileNotFoundError or similar",
            isinstance(load_error, (FileNotFoundError, OSError)),
            f"Got {type(load_error).__name__}: {load_error}",
        )

        # ── Test 6: Overwrite and reload ──────────────────────────────
        print("\n[Test 6] Overwrite checkpoint and verify new weights")
        with torch.no_grad():
            for p in model.parameters():
                p.fill_(0.99)
        meta2 = {
            "model_state_dict": model.state_dict(),
            "trm_type": "atp_executor",
            "version": 2,
            "epoch": 100,
            "loss": 0.005,
        }
        torch.save(meta2, ckpt_path)
        loaded2 = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        test(
            "Overwritten checkpoint has version 2",
            loaded2["version"] == 2,
            f"Got version {loaded2.get('version')}",
        )
        # Check the weights are 0.99, not 0.42
        fc1_weight = loaded2["model_state_dict"]["fc1.weight"]
        test(
            "Overwritten weights reflect new values",
            torch.allclose(fc1_weight, torch.full_like(fc1_weight, 0.99)),
            "Weights do not match 0.99",
        )

    finally:
        # Cleanup temp directory
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)
