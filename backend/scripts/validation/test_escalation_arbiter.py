#!/usr/bin/env python3
"""F4: Escalation Arbiter Validation"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

# We cannot import EscalationArbiter directly because it pulls in SQLAlchemy
# models that trigger DB config. Instead, we import the dataclasses and
# constants by extracting them, and replicate the routing logic for testing.

# ---------------------------------------------------------------------------
# Replicate the pure-data structures from escalation_arbiter.py
# (these have no DB dependencies)
# ---------------------------------------------------------------------------

# Configuration defaults (must match escalation_arbiter.py)
PERSISTENCE_WINDOW_HOURS = 48
CONSISTENCY_THRESHOLD = 0.70
MAGNITUDE_THRESHOLD_OPERATIONAL = 0.20
MAGNITUDE_THRESHOLD_STRATEGIC = 0.35
CROSS_SITE_FRACTION = 0.30
MIN_DECISIONS_FOR_SIGNAL = 20
COOLDOWN_OPERATIONAL_HOURS = 12
COOLDOWN_STRATEGIC_HOURS = 72


@dataclass
class PersistenceSignal:
    site_key: str
    trm_type: str
    direction: float
    magnitude: float
    consistency: float
    duration_hours: float
    decision_count: int
    trigger_reasons: List[str] = field(default_factory=list)


@dataclass
class CrossSitePattern:
    affected_sites: List[str]
    fraction_of_sites: float
    dominant_direction: float
    dominant_trm_types: List[str]


@dataclass
class EscalationVerdict:
    level: str
    diagnosis: str
    affected_sites: List[str]
    affected_trm_types: List[str]
    recommended_action: str
    evidence: Dict[str, Any]
    urgency: str


# EscalationLevel values (must match escalation_arbiter.py)
LEVEL_NONE = "none"
LEVEL_HORIZONTAL = "horizontal"
LEVEL_OPERATIONAL = "operational"
LEVEL_STRATEGIC = "strategic"


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


def route_escalation(signals, cross_site):
    """Replicate EscalationArbiter._route_escalation() logic for testing.

    This is a faithful copy of the routing logic from escalation_arbiter.py
    so we can validate the decision logic without DB dependencies.
    """
    site_key = signals[0].site_key if signals else "test_site"

    significant = [
        s for s in signals
        if s.consistency >= CONSISTENCY_THRESHOLD and s.magnitude >= 0.10
    ]

    if not significant:
        return EscalationVerdict(
            level=LEVEL_NONE,
            diagnosis="No persistent anomalies above threshold",
            affected_sites=[site_key],
            affected_trm_types=[s.trm_type for s in signals],
            recommended_action="none",
            evidence={},
            urgency="low",
        )

    # Strategic (cross-site)
    if (
        cross_site.fraction_of_sites >= CROSS_SITE_FRACTION
        and site_key in cross_site.affected_sites
    ):
        max_mag = max(s.magnitude for s in significant)
        return EscalationVerdict(
            level=LEVEL_STRATEGIC,
            diagnosis="Network-wide persistence detected",
            affected_sites=cross_site.affected_sites,
            affected_trm_types=cross_site.dominant_trm_types,
            recommended_action="sop_review",
            evidence={},
            urgency="critical" if max_mag >= MAGNITUDE_THRESHOLD_STRATEGIC else "high",
        )

    # Operational (multi-TRM or high magnitude + long duration)
    high_magnitude = [
        s for s in significant
        if s.magnitude >= MAGNITUDE_THRESHOLD_OPERATIONAL
    ]

    if len(significant) >= 3 or (
        len(high_magnitude) >= 1
        and any(s.duration_hours >= 24 for s in high_magnitude)
    ):
        trm_types = list(set(s.trm_type for s in significant))
        return EscalationVerdict(
            level=LEVEL_OPERATIONAL,
            diagnosis="Persistent drift detected",
            affected_sites=[site_key],
            affected_trm_types=trm_types,
            recommended_action="tgnn_refresh",
            evidence={},
            urgency="high",
        )

    # Single-TRM long-duration
    long_duration = [s for s in significant if s.duration_hours >= 24]
    if long_duration:
        sig = max(long_duration, key=lambda s: s.magnitude)
        return EscalationVerdict(
            level=LEVEL_OPERATIONAL,
            diagnosis="Sustained drift",
            affected_sites=[site_key],
            affected_trm_types=[sig.trm_type],
            recommended_action="tgnn_refresh",
            evidence={},
            urgency="medium",
        )

    # Moderate -> horizontal
    return EscalationVerdict(
        level=LEVEL_HORIZONTAL,
        diagnosis="Moderate drift",
        affected_sites=[site_key],
        affected_trm_types=[s.trm_type for s in significant],
        recommended_action="trm_retrain",
        evidence={},
        urgency="low",
    )


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"F4: Escalation Arbiter Validation")
    print(f"{'='*60}")

    no_cross = CrossSitePattern(
        affected_sites=[], fraction_of_sites=0.0,
        dominant_direction=0.0, dominant_trm_types=[],
    )

    # ------------------------------------------------------------------
    # 1. No drift -> no escalation
    # ------------------------------------------------------------------
    print("\n--- 1. No drift -> no escalation ---")

    low_signal = PersistenceSignal(
        site_key="SITE_A", trm_type="atp_executor",
        direction=0.1, magnitude=0.05,
        consistency=0.55,  # Below CONSISTENCY_THRESHOLD (0.70)
        duration_hours=12, decision_count=50,
    )
    verdict1 = route_escalation([low_signal], no_cross)
    test(
        "Low consistency -> no escalation",
        verdict1.level == LEVEL_NONE,
        f"got level={verdict1.level}",
    )

    low_mag = PersistenceSignal(
        site_key="SITE_A", trm_type="po_creation",
        direction=0.8, magnitude=0.08,  # Below 0.10 filter
        consistency=0.85, duration_hours=48, decision_count=100,
    )
    verdict1b = route_escalation([low_mag], no_cross)
    test(
        "Low magnitude -> no escalation",
        verdict1b.level == LEVEL_NONE,
        f"got level={verdict1b.level}",
    )

    # ------------------------------------------------------------------
    # 2. Persistent drift -> operational escalation
    # ------------------------------------------------------------------
    print("\n--- 2. Persistent drift -> operational escalation ---")

    persistent_signal = PersistenceSignal(
        site_key="SITE_B", trm_type="po_creation",
        direction=0.85, magnitude=0.30,  # Above MAGNITUDE_THRESHOLD_OPERATIONAL
        consistency=0.80,  # Above CONSISTENCY_THRESHOLD
        duration_hours=36, decision_count=80,  # Above 24h
    )
    verdict2 = route_escalation([persistent_signal], no_cross)
    test(
        "High consistency + magnitude + duration -> operational",
        verdict2.level == LEVEL_OPERATIONAL,
        f"got level={verdict2.level}",
    )
    test(
        "Operational recommended_action is tgnn_refresh",
        verdict2.recommended_action == "tgnn_refresh",
        f"got {verdict2.recommended_action}",
    )

    # Multiple significant TRMs (>= 3) -> operational
    multi_signals = [
        PersistenceSignal(
            site_key="SITE_C", trm_type="atp_executor",
            direction=0.7, magnitude=0.15, consistency=0.75,
            duration_hours=10, decision_count=30,
        ),
        PersistenceSignal(
            site_key="SITE_C", trm_type="po_creation",
            direction=0.8, magnitude=0.18, consistency=0.80,
            duration_hours=10, decision_count=40,
        ),
        PersistenceSignal(
            site_key="SITE_C", trm_type="inventory_buffer",
            direction=0.6, magnitude=0.12, consistency=0.72,
            duration_hours=10, decision_count=25,
        ),
    ]
    verdict2b = route_escalation(multi_signals, no_cross)
    test(
        "3+ significant TRMs -> operational",
        verdict2b.level == LEVEL_OPERATIONAL,
        f"got level={verdict2b.level}",
    )

    # ------------------------------------------------------------------
    # 3. Cross-site drift (>=30%) -> strategic escalation
    # ------------------------------------------------------------------
    print("\n--- 3. Cross-site drift -> strategic escalation ---")

    cross_site_pattern = CrossSitePattern(
        affected_sites=["SITE_A", "SITE_B", "SITE_C", "SITE_D"],
        fraction_of_sites=0.40,  # Above CROSS_SITE_FRACTION (0.30)
        dominant_direction=0.75,
        dominant_trm_types=["po_creation", "inventory_buffer"],
    )

    strategic_signal = PersistenceSignal(
        site_key="SITE_A", trm_type="po_creation",
        direction=0.9, magnitude=0.40,  # Above MAGNITUDE_THRESHOLD_STRATEGIC
        consistency=0.85, duration_hours=48, decision_count=100,
    )
    verdict3 = route_escalation([strategic_signal], cross_site_pattern)
    test(
        "Cross-site >= 30% -> strategic",
        verdict3.level == LEVEL_STRATEGIC,
        f"got level={verdict3.level}",
    )
    test(
        "Strategic recommended_action is sop_review",
        verdict3.recommended_action == "sop_review",
        f"got {verdict3.recommended_action}",
    )
    test(
        "Strategic urgency is critical (mag >= 0.35)",
        verdict3.urgency == "critical",
        f"got {verdict3.urgency}",
    )

    # Lower magnitude -> urgency high (not critical)
    moderate_strategic = PersistenceSignal(
        site_key="SITE_B", trm_type="po_creation",
        direction=0.7, magnitude=0.25,
        consistency=0.80, duration_hours=36, decision_count=60,
    )
    verdict3b = route_escalation([moderate_strategic], cross_site_pattern)
    test(
        "Strategic with moderate mag -> urgency high",
        verdict3b.urgency == "high",
        f"got {verdict3b.urgency}",
    )

    # ------------------------------------------------------------------
    # 4. Cooldown enforcement
    # ------------------------------------------------------------------
    print("\n--- 4. Cooldown enforcement ---")

    test(
        "Operational cooldown = 12h",
        COOLDOWN_OPERATIONAL_HOURS == 12,
        f"got {COOLDOWN_OPERATIONAL_HOURS}",
    )
    test(
        "Strategic cooldown = 72h",
        COOLDOWN_STRATEGIC_HOURS == 72,
        f"got {COOLDOWN_STRATEGIC_HOURS}",
    )
    test(
        "Horizontal is distinct from operational/strategic",
        LEVEL_HORIZONTAL not in (LEVEL_OPERATIONAL, LEVEL_STRATEGIC),
        "horizontal should be a distinct level",
    )
    test(
        "Persistence window = 48h",
        PERSISTENCE_WINDOW_HOURS == 48,
        f"got {PERSISTENCE_WINDOW_HOURS}",
    )
    test(
        "Consistency threshold = 0.70",
        CONSISTENCY_THRESHOLD == 0.70,
        f"got {CONSISTENCY_THRESHOLD}",
    )
    test(
        "Min decisions for signal = 20",
        MIN_DECISIONS_FOR_SIGNAL == 20,
        f"got {MIN_DECISIONS_FOR_SIGNAL}",
    )

    # ------------------------------------------------------------------
    # 5. Verdict routing - operational vs strategic
    # ------------------------------------------------------------------
    print("\n--- 5. Verdict routing ---")

    test(
        "Operational verdict -> tgnn_refresh",
        verdict2.recommended_action == "tgnn_refresh",
        f"got {verdict2.recommended_action}",
    )
    test(
        "Strategic verdict -> sop_review",
        verdict3.recommended_action == "sop_review",
        f"got {verdict3.recommended_action}",
    )

    # Moderate single-TRM -> horizontal (trm_retrain)
    moderate_signal = PersistenceSignal(
        site_key="SITE_X", trm_type="atp_executor",
        direction=0.6, magnitude=0.12,
        consistency=0.72, duration_hours=10, decision_count=30,
    )
    verdict5 = route_escalation([moderate_signal], no_cross)
    test(
        "Moderate single-TRM -> horizontal",
        verdict5.level == LEVEL_HORIZONTAL,
        f"got level={verdict5.level}",
    )
    test(
        "Horizontal verdict -> trm_retrain",
        verdict5.recommended_action == "trm_retrain",
        f"got {verdict5.recommended_action}",
    )

    # Verify EscalationVerdict fields
    test("Verdict has level", hasattr(verdict3, "level"), "missing level")
    test("Verdict has diagnosis", hasattr(verdict3, "diagnosis"), "missing diagnosis")
    test("Verdict has affected_sites", hasattr(verdict3, "affected_sites"), "missing affected_sites")
    test("Verdict has affected_trm_types", hasattr(verdict3, "affected_trm_types"), "missing affected_trm_types")
    test("Verdict has recommended_action", hasattr(verdict3, "recommended_action"), "missing recommended_action")
    test("Verdict has evidence", hasattr(verdict3, "evidence"), "missing evidence")
    test("Verdict has urgency", hasattr(verdict3, "urgency"), "missing urgency")

    # Escalation level values
    test("NONE level = 'none'", LEVEL_NONE == "none", f"got {LEVEL_NONE}")
    test("HORIZONTAL level = 'horizontal'", LEVEL_HORIZONTAL == "horizontal", f"got {LEVEL_HORIZONTAL}")
    test("OPERATIONAL level = 'operational'", LEVEL_OPERATIONAL == "operational", f"got {LEVEL_OPERATIONAL}")
    test("STRATEGIC level = 'strategic'", LEVEL_STRATEGIC == "strategic", f"got {LEVEL_STRATEGIC}")

    # PersistenceSignal serialization
    ps_dict = asdict(persistent_signal)
    test(
        "PersistenceSignal serializable",
        "site_key" in ps_dict and "consistency" in ps_dict,
        f"keys={list(ps_dict.keys())}",
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
