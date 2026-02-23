"""
Unit tests for hive signal primitives.

Tests: HiveSignal decay, HiveSignalType enum, UrgencyVector, HiveSignalBus,
       HiveHealthMetrics.

Sprint 1 validation criteria:
  - Signal decay math correct (half_life=30min, verify at t=0/15/30/60)
  - Ring buffer evicts oldest on overflow
  - UrgencyVector.snapshot() returns frozen copy
  - All unit tests pass
"""

import math
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.services.powell.hive_signal import (
    BUILDER_SIGNALS,
    DECAY_THRESHOLD,
    FORAGER_SIGNALS,
    GUARD_SIGNALS,
    NURSE_SIGNALS,
    SCOUT_SIGNALS,
    TGNN_SIGNALS,
    HiveSignal,
    HiveSignalBus,
    HiveSignalType,
    UrgencyVector,
)
from app.services.powell.hive_health import HiveHealthMetrics


# ============================================================
# HiveSignalType enum
# ============================================================

class TestHiveSignalType:
    def test_total_count(self):
        """25 total signal types across 5 castes + tGNN."""
        assert len(HiveSignalType) == 25

    def test_caste_coverage(self):
        """Every signal type belongs to exactly one caste group."""
        all_caste = SCOUT_SIGNALS | FORAGER_SIGNALS | NURSE_SIGNALS | GUARD_SIGNALS | BUILDER_SIGNALS | TGNN_SIGNALS
        all_types = set(HiveSignalType)
        assert all_caste == all_types, f"Missing: {all_types - all_caste}"

    def test_caste_sizes(self):
        assert len(SCOUT_SIGNALS) == 5
        assert len(FORAGER_SIGNALS) == 5
        assert len(NURSE_SIGNALS) == 3
        assert len(GUARD_SIGNALS) == 4
        assert len(BUILDER_SIGNALS) == 4
        assert len(TGNN_SIGNALS) == 4

    def test_string_enum(self):
        """Signal types are string-valued for JSON serialization."""
        assert HiveSignalType.ATP_SHORTAGE == "atp_shortage"
        assert HiveSignalType.ATP_SHORTAGE.value == "atp_shortage"

    def test_no_caste_overlap(self):
        """No signal type appears in multiple caste groups."""
        groups = [SCOUT_SIGNALS, FORAGER_SIGNALS, NURSE_SIGNALS,
                  GUARD_SIGNALS, BUILDER_SIGNALS, TGNN_SIGNALS]
        for i, g1 in enumerate(groups):
            for g2 in groups[i + 1:]:
                assert g1.isdisjoint(g2)


# ============================================================
# HiveSignal decay
# ============================================================

class TestHiveSignalDecay:
    def test_strength_at_t0(self):
        """At t=0, current_strength equals urgency."""
        signal = HiveSignal(
            urgency=0.8,
            timestamp=datetime.now(timezone.utc),
        )
        assert abs(signal.current_strength - 0.8) < 0.01

    def test_strength_at_half_life(self):
        """At t=half_life, strength should be ~50% of urgency."""
        now = datetime.now(timezone.utc)
        signal = HiveSignal(
            urgency=1.0,
            half_life_minutes=30.0,
            timestamp=now - timedelta(minutes=30),
        )
        assert abs(signal.current_strength - 0.5) < 0.01

    def test_strength_at_15min(self):
        """At t=15min (half of half_life=30), strength ~0.707."""
        now = datetime.now(timezone.utc)
        signal = HiveSignal(
            urgency=1.0,
            half_life_minutes=30.0,
            timestamp=now - timedelta(minutes=15),
        )
        expected = math.exp(-0.693147 * 15 / 30)  # ~0.707
        assert abs(signal.current_strength - expected) < 0.02

    def test_strength_at_60min(self):
        """At t=60min (2 half-lives), strength ~0.25."""
        now = datetime.now(timezone.utc)
        signal = HiveSignal(
            urgency=1.0,
            half_life_minutes=30.0,
            timestamp=now - timedelta(minutes=60),
        )
        assert abs(signal.current_strength - 0.25) < 0.02

    def test_strength_decays_to_zero(self):
        """After many half-lives, signal is effectively dead."""
        now = datetime.now(timezone.utc)
        signal = HiveSignal(
            urgency=1.0,
            half_life_minutes=30.0,
            timestamp=now - timedelta(minutes=300),
        )
        assert signal.current_strength < DECAY_THRESHOLD
        assert not signal.is_alive

    def test_is_alive_fresh_signal(self):
        signal = HiveSignal(urgency=0.5, timestamp=datetime.now(timezone.utc))
        assert signal.is_alive

    def test_zero_urgency_never_alive(self):
        signal = HiveSignal(urgency=0.0, timestamp=datetime.now(timezone.utc))
        assert not signal.is_alive  # 0.0 <= threshold

    def test_custom_half_life(self):
        """Short half-life decays faster."""
        now = datetime.now(timezone.utc)
        signal = HiveSignal(
            urgency=1.0,
            half_life_minutes=5.0,
            timestamp=now - timedelta(minutes=5),
        )
        assert abs(signal.current_strength - 0.5) < 0.01

    def test_future_timestamp_returns_urgency(self):
        """If timestamp is in the future, return full urgency."""
        signal = HiveSignal(
            urgency=0.9,
            timestamp=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        assert abs(signal.current_strength - 0.9) < 0.01

    def test_to_dict_serialization(self):
        signal = HiveSignal(
            source_trm="atp_executor",
            signal_type=HiveSignalType.ATP_SHORTAGE,
            urgency=0.8,
            direction="shortage",
            magnitude=500.0,
            product_id="PROD-001",
            payload={"shortfall_qty": 200},
        )
        d = signal.to_dict()
        assert d["source_trm"] == "atp_executor"
        assert d["signal_type"] == "atp_shortage"
        assert d["urgency"] == 0.8
        assert d["direction"] == "shortage"
        assert d["product_id"] == "PROD-001"
        assert "current_strength" in d
        assert isinstance(d["payload"], dict)


# ============================================================
# UrgencyVector
# ============================================================

class TestUrgencyVector:
    def test_initial_state(self):
        uv = UrgencyVector()
        for trm_name in UrgencyVector.TRM_INDICES:
            val, direction, ts = uv.read(trm_name)
            assert val == 0.0
            assert direction == "neutral"
            assert ts is None

    def test_update_and_read(self):
        uv = UrgencyVector()
        uv.update("atp_executor", 0.8, "shortage")
        val, direction, ts = uv.read("atp_executor")
        assert val == 0.8
        assert direction == "shortage"
        assert ts is not None

    def test_clamp_urgency(self):
        """Urgency is clamped to [0.0, 1.0]."""
        uv = UrgencyVector()
        uv.update("po_creation", 1.5, "shortage")
        val, _, _ = uv.read("po_creation")
        assert val == 1.0

        uv.update("po_creation", -0.3, "neutral")
        val, _, _ = uv.read("po_creation")
        assert val == 0.0

    def test_invalid_trm_name(self):
        uv = UrgencyVector()
        with pytest.raises(ValueError, match="Unknown TRM"):
            uv.update("nonexistent_trm", 0.5)
        with pytest.raises(ValueError, match="Unknown TRM"):
            uv.read("nonexistent_trm")

    def test_invalid_direction(self):
        uv = UrgencyVector()
        with pytest.raises(ValueError, match="Invalid direction"):
            uv.update("atp_executor", 0.5, "invalid_dir")

    def test_snapshot_is_frozen_copy(self):
        """snapshot() returns a new dict; mutating it doesn't affect the vector."""
        uv = UrgencyVector()
        uv.update("atp_executor", 0.7, "shortage")
        snap = uv.snapshot()

        # Mutate the snapshot
        snap["values"][0] = 999.0

        # Original unchanged
        val, _, _ = uv.read("atp_executor")
        assert val == 0.7

    def test_values_array(self):
        uv = UrgencyVector()
        uv.update("atp_executor", 0.5, "shortage")
        uv.update("to_execution", 0.3, "relief")
        arr = uv.values_array()
        assert len(arr) == 11
        assert arr[0] == 0.5  # atp_executor
        assert arr[10] == 0.3  # to_execution

    def test_max_urgency(self):
        uv = UrgencyVector()
        uv.update("quality", 0.9, "risk")
        uv.update("atp_executor", 0.3, "shortage")
        name, val, direction = uv.max_urgency()
        assert name == "quality"
        assert val == 0.9
        assert direction == "risk"

    def test_reset(self):
        uv = UrgencyVector()
        uv.update("atp_executor", 0.8, "shortage")
        uv.update("po_creation", 0.5, "surplus")
        uv.reset()
        for trm in UrgencyVector.TRM_INDICES:
            val, direction, ts = uv.read(trm)
            assert val == 0.0
            assert direction == "neutral"
            assert ts is None

    def test_all_11_trm_slots(self):
        """All 11 TRM names are valid and occupy unique indices."""
        uv = UrgencyVector()
        indices_seen = set()
        for name, idx in UrgencyVector.TRM_INDICES.items():
            assert idx not in indices_seen
            indices_seen.add(idx)
            uv.update(name, 0.1 * (idx + 1), "neutral")
        assert len(indices_seen) == 11

    def test_thread_safety(self):
        """Concurrent updates don't corrupt the vector."""
        uv = UrgencyVector()
        errors = []

        def updater(trm_name: str, urgency: float):
            try:
                for _ in range(100):
                    uv.update(trm_name, urgency, "shortage")
                    uv.read(trm_name)
                    uv.snapshot()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=updater, args=("atp_executor", 0.5)),
            threading.Thread(target=updater, args=("po_creation", 0.3)),
            threading.Thread(target=updater, args=("quality", 0.9)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0


# ============================================================
# HiveSignalBus
# ============================================================

class TestHiveSignalBus:
    def _make_signal(
        self,
        source: str = "atp_executor",
        stype: HiveSignalType = HiveSignalType.ATP_SHORTAGE,
        urgency: float = 0.8,
        direction: str = "shortage",
        age_minutes: float = 0,
    ) -> HiveSignal:
        return HiveSignal(
            source_trm=source,
            signal_type=stype,
            urgency=urgency,
            direction=direction,
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=age_minutes),
        )

    def test_emit_and_read(self):
        bus = HiveSignalBus()
        signal = self._make_signal()
        bus.emit(signal)
        results = bus.read("po_creation")
        assert len(results) == 1
        assert results[0].signal_type == HiveSignalType.ATP_SHORTAGE

    def test_self_exclusion(self):
        """TRM does not read its own signals."""
        bus = HiveSignalBus()
        bus.emit(self._make_signal(source="atp_executor"))
        results = bus.read("atp_executor")
        assert len(results) == 0

    def test_type_filter(self):
        bus = HiveSignalBus()
        bus.emit(self._make_signal(stype=HiveSignalType.ATP_SHORTAGE))
        bus.emit(self._make_signal(stype=HiveSignalType.DEMAND_SURGE, source="order_tracking"))
        bus.emit(self._make_signal(stype=HiveSignalType.PO_EXPEDITE, source="po_creation"))

        results = bus.read("rebalancing", types={HiveSignalType.ATP_SHORTAGE})
        assert len(results) == 1
        assert results[0].signal_type == HiveSignalType.ATP_SHORTAGE

    def test_temporal_filter(self):
        bus = HiveSignalBus()
        old = self._make_signal(age_minutes=10)
        new = self._make_signal(age_minutes=0, source="order_tracking",
                                stype=HiveSignalType.ORDER_EXCEPTION)
        bus.emit(old)
        bus.emit(new)

        since = datetime.now(timezone.utc) - timedelta(minutes=5)
        results = bus.read("po_creation", since=since)
        assert len(results) == 1
        assert results[0].signal_type == HiveSignalType.ORDER_EXCEPTION

    def test_decay_filter(self):
        """Decayed signals are excluded from read results."""
        bus = HiveSignalBus()
        dead = self._make_signal(urgency=0.1, age_minutes=300)  # long dead
        alive = self._make_signal(urgency=0.8, age_minutes=0, source="order_tracking",
                                  stype=HiveSignalType.ORDER_EXCEPTION)
        bus.emit(dead)
        bus.emit(alive)

        results = bus.read("po_creation")
        assert len(results) == 1
        assert results[0].signal_type == HiveSignalType.ORDER_EXCEPTION

    def test_ring_buffer_overflow(self):
        """Oldest signals evicted when buffer is full."""
        bus = HiveSignalBus(max_signals=5)
        for i in range(10):
            bus.emit(self._make_signal(
                source=f"trm_{i % 3}",
                stype=HiveSignalType.ATP_SHORTAGE,
                urgency=0.5 + i * 0.01,
            ))
        assert len(bus) == 5
        # First 5 signals should be gone, only last 5 remain
        results = bus.read("consumer")
        urgencies = [s.urgency for s in results]
        assert min(urgencies) >= 0.55  # signals 5-9

    def test_read_latest_by_type(self):
        bus = HiveSignalBus()
        bus.emit(self._make_signal(urgency=0.5, source="atp_executor"))
        bus.emit(self._make_signal(urgency=0.9, source="order_tracking",
                                   stype=HiveSignalType.ATP_SHORTAGE))
        latest = bus.read_latest_by_type(HiveSignalType.ATP_SHORTAGE, consumer_trm="po_creation")
        assert latest is not None
        assert latest.urgency == 0.9

    def test_read_latest_by_type_none(self):
        bus = HiveSignalBus()
        result = bus.read_latest_by_type(HiveSignalType.MO_RELEASED)
        assert result is None

    def test_active_signals(self):
        bus = HiveSignalBus()
        bus.emit(self._make_signal(urgency=0.8))
        bus.emit(self._make_signal(urgency=0.1, age_minutes=300))  # dead
        active = bus.active_signals()
        assert len(active) == 1

    def test_signal_summary(self):
        bus = HiveSignalBus()
        bus.emit(self._make_signal(stype=HiveSignalType.ATP_SHORTAGE))
        bus.emit(self._make_signal(stype=HiveSignalType.ATP_SHORTAGE, source="x"))
        bus.emit(self._make_signal(stype=HiveSignalType.PO_EXPEDITE, source="y"))
        summary = bus.signal_summary()
        assert summary["atp_shortage"] == 2
        assert summary["po_expedite"] == 1

    def test_clear(self):
        bus = HiveSignalBus()
        bus.emit(self._make_signal())
        bus.urgency.update("atp_executor", 0.8, "shortage")
        bus.clear()
        assert len(bus) == 0
        val, _, _ = bus.urgency.read("atp_executor")
        assert val == 0.0

    def test_stats(self):
        bus = HiveSignalBus(max_signals=100)
        bus.emit(self._make_signal())
        bus.read("consumer")
        stats = bus.stats()
        assert stats["total_in_buffer"] == 1
        assert stats["capacity"] == 100
        assert stats["total_emitted"] == 1
        assert stats["total_reads"] == 1

    def test_to_context_dict(self):
        bus = HiveSignalBus()
        bus.emit(self._make_signal())
        ctx = bus.to_context_dict()
        assert "active_signal_count" in ctx
        assert "signals" in ctx
        assert "urgency_vector" in ctx
        assert "summary" in ctx
        assert ctx["active_signal_count"] == 1

    def test_empty_bus_read(self):
        """Reading from empty bus returns empty list."""
        bus = HiveSignalBus()
        results = bus.read("atp_executor")
        assert results == []

    def test_thread_safety(self):
        """Concurrent emit/read operations don't crash."""
        bus = HiveSignalBus(max_signals=50)
        errors = []

        def emitter():
            try:
                for _ in range(100):
                    bus.emit(self._make_signal(urgency=0.5))
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(100):
                    bus.read("consumer")
                    bus.active_signals()
                    bus.signal_summary()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=emitter),
            threading.Thread(target=emitter),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0


# ============================================================
# HiveHealthMetrics
# ============================================================

class TestHiveHealthMetrics:
    def test_from_empty_bus(self):
        bus = HiveSignalBus()
        metrics = HiveHealthMetrics.from_signal_bus(bus, site_key="SITE-001")
        assert metrics.site_key == "SITE-001"
        assert metrics.mean_urgency == 0.0
        assert metrics.max_urgency == 0.0
        assert metrics.active_signal_count == 0
        assert metrics.is_quiet
        assert not metrics.is_stressed

    def test_from_active_bus(self):
        bus = HiveSignalBus()
        bus.urgency.update("atp_executor", 0.8, "shortage")
        bus.urgency.update("quality", 0.6, "risk")
        bus.emit(HiveSignal(
            source_trm="atp_executor",
            signal_type=HiveSignalType.ATP_SHORTAGE,
            urgency=0.8,
            direction="shortage",
        ))
        metrics = HiveHealthMetrics.from_signal_bus(bus, site_key="SITE-002")
        assert metrics.max_urgency == 0.8
        assert metrics.max_urgency_trm == "atp_executor"
        assert metrics.active_signal_count == 1
        assert not metrics.is_quiet

    def test_conflict_detection(self):
        bus = HiveSignalBus()
        bus.urgency.update("atp_executor", 0.7, "shortage")
        bus.urgency.update("rebalancing", 0.5, "surplus")
        metrics = HiveHealthMetrics.from_signal_bus(bus)
        assert metrics.shortage_count == 1
        assert metrics.surplus_count == 1
        assert metrics.has_conflict

    def test_stressed_high_urgency(self):
        bus = HiveSignalBus()
        # Set all TRMs to high urgency to push mean above 0.6
        for trm in UrgencyVector.TRM_INDICES:
            bus.urgency.update(trm, 0.8, "shortage")
        metrics = HiveHealthMetrics.from_signal_bus(bus)
        assert metrics.is_stressed
        assert metrics.mean_urgency > 0.6

    def test_to_dict(self):
        bus = HiveSignalBus()
        bus.urgency.update("atp_executor", 0.5, "shortage")
        metrics = HiveHealthMetrics.from_signal_bus(bus, site_key="SITE-003", cycle_id="CYC-001")
        d = metrics.to_dict()
        assert d["site_key"] == "SITE-003"
        assert d["cycle_id"] == "CYC-001"
        assert len(d["urgency_values"]) == 11
        assert "mean_urgency" in d
        assert "has_conflict" in d


# ============================================================
# Integration: signal cascade
# ============================================================

class TestSignalCascade:
    """Test a realistic signal cascade: ATP shortage → PO expedite → rebalance."""

    def test_atp_shortage_cascade(self):
        bus = HiveSignalBus()

        # Phase 1 (SENSE): ATP detects shortage
        atp_signal = HiveSignal(
            source_trm="atp_executor",
            signal_type=HiveSignalType.ATP_SHORTAGE,
            urgency=0.8,
            direction="shortage",
            magnitude=500.0,
            product_id="PROD-001",
            payload={"shortfall_qty": 200},
        )
        bus.emit(atp_signal)
        bus.urgency.update("atp_executor", 0.8, "shortage")

        # Phase 3 (ACQUIRE): PO reads ATP_SHORTAGE
        po_signals = bus.read(
            "po_creation",
            types={HiveSignalType.ATP_SHORTAGE, HiveSignalType.DEMAND_SURGE},
        )
        assert len(po_signals) == 1
        assert po_signals[0].urgency == 0.8
        assert po_signals[0].payload["shortfall_qty"] == 200

        # PO emits expedite
        po_signal = HiveSignal(
            source_trm="po_creation",
            signal_type=HiveSignalType.PO_EXPEDITE,
            urgency=0.7,
            direction="relief",
            payload={"eta_days": 5},
        )
        bus.emit(po_signal)
        bus.urgency.update("po_creation", 0.7, "relief")

        # Phase 3 (ACQUIRE): Rebalancing reads both signals
        rebal_signals = bus.read(
            "rebalancing",
            types={HiveSignalType.ATP_SHORTAGE, HiveSignalType.PO_EXPEDITE},
        )
        assert len(rebal_signals) == 2
        types_found = {s.signal_type for s in rebal_signals}
        assert HiveSignalType.ATP_SHORTAGE in types_found
        assert HiveSignalType.PO_EXPEDITE in types_found

        # Verify urgency vector state
        atp_val, atp_dir, _ = bus.urgency.read("atp_executor")
        assert atp_val == 0.8
        assert atp_dir == "shortage"

        po_val, po_dir, _ = bus.urgency.read("po_creation")
        assert po_val == 0.7
        assert po_dir == "relief"

        # Health metrics show mixed state
        metrics = HiveHealthMetrics.from_signal_bus(bus, site_key="TEST")
        assert metrics.active_signal_count == 2
        assert metrics.shortage_count >= 1
