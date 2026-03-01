"""
Escalation Arbiter — Vertical Decision Routing Between Tiers

Detects persistent anomalies at the execution tier (TRMs) and routes
to operational (tGNN) or strategic (GraphSAGE/S&OP) replanning.

Theoretical foundations (see docs/ESCALATION_ARCHITECTURE.md):
- Kahneman: System 1 (TRM) persistent failure → activate System 2 (tGNN/GraphSAGE)
- Boyd OODA: Inner loop anomaly → trigger outer loop iteration
- Powell: Belief state Bₜ divergence → reframe at higher modeling tier
- SOFAI (arxiv:2110.01834): Meta-Cognitive module routing System 1 ↔ System 2

The core insight: when TRMs consistently correct in the same direction
(always ordering more, always buffering up), the policy parameters (θ)
are wrong — not the execution decisions. This requires replanning at a
higher tier, not retraining the execution model.

Pipeline:
1. Every 2h, evaluate_all_sites() queries recent TRM decisions
2. For each (site, trm_type), compute persistence signals (direction, magnitude, consistency)
3. Detect cross-site patterns (fraction of sites showing same drift)
4. Route: horizontal (CDC retrain) | vertical-operational (tGNN refresh) | vertical-strategic (S&OP review)
5. Log to powell_escalation_log for audit trail

Schedule: every 2 hours at :40 (via relearning_jobs.py)
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
import logging
import math

from sqlalchemy.orm import Session
from sqlalchemy import func, text, and_, or_

from app.models.escalation_log import PowellEscalationLog
from app.services.powell.cdc_monitor import TriggerReason, ReplanAction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration defaults (overridable per tenant via SiteAgentConfig)
# ---------------------------------------------------------------------------

PERSISTENCE_WINDOW_HOURS = 48         # Look-back window for pattern detection
CONSISTENCY_THRESHOLD = 0.70          # 70% same-direction → significant
MAGNITUDE_THRESHOLD_OPERATIONAL = 0.20  # 20% avg adjustment → operational
MAGNITUDE_THRESHOLD_STRATEGIC = 0.35    # 35% avg adjustment → strategic
CROSS_SITE_FRACTION = 0.30           # 30% of sites showing pattern → strategic
MIN_DECISIONS_FOR_SIGNAL = 20         # Minimum decisions before pattern is meaningful
COOLDOWN_OPERATIONAL_HOURS = 12       # Min time between operational escalations
COOLDOWN_STRATEGIC_HOURS = 72         # Min time between strategic escalations


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PersistenceSignal:
    """Statistical summary of persistent directional drift in TRM decisions.

    When a TRM consistently adjusts in the same direction (e.g., always
    ordering more than the deterministic engine suggests), this signals
    that the underlying policy parameters (θ) may be miscalibrated.
    """
    site_key: str
    trm_type: str
    direction: float           # Mean adjustment direction [-1, +1]
    magnitude: float           # Mean |adjustment| as fraction of baseline
    consistency: float         # Fraction of adjustments in dominant direction [0, 1]
    duration_hours: float      # How long the pattern has persisted
    decision_count: int        # Number of decisions in the window
    trigger_reasons: List[str] = field(default_factory=list)


@dataclass
class CrossSitePattern:
    """Network-wide pattern detection across multiple sites."""
    affected_sites: List[str]
    fraction_of_sites: float   # Fraction of total sites showing the pattern
    dominant_direction: float  # Network-wide adjustment direction
    dominant_trm_types: List[str]  # Which TRM types show the pattern


@dataclass
class EscalationVerdict:
    """The Arbiter's diagnosis and routing decision.

    Maps to Powell's framing: which tier's policy class should handle this?
    - horizontal → VFA (retrain TRM)
    - operational → CFA/VFA bridge (tGNN refresh)
    - strategic → CFA (S&OP policy review)
    """
    level: str                 # "none", "horizontal", "operational", "strategic"
    diagnosis: str             # Human-readable explanation
    affected_sites: List[str]
    affected_trm_types: List[str]
    recommended_action: str    # "trm_retrain", "tgnn_refresh", "sop_review"
    evidence: Dict[str, Any]  # Serialized persistence/cross-site data
    urgency: str              # "low", "medium", "high", "critical"


class EscalationLevel(str, Enum):
    """Escalation routing levels."""
    NONE = "none"
    HORIZONTAL = "horizontal"       # CDC retrain (existing loop)
    OPERATIONAL = "operational"     # tGNN refresh (new)
    STRATEGIC = "strategic"         # S&OP policy review (new)


# ---------------------------------------------------------------------------
# Escalation Arbiter Service
# ---------------------------------------------------------------------------

class EscalationArbiter:
    """Vertical escalation between decision tiers.

    Monitors TRM decision patterns for persistent directional drift.
    When execution-level corrections consistently push in the same
    direction, diagnoses whether operational or strategic replanning
    is needed.

    Architecture role:
    - Kahneman: The "Lazy Controller" that activates System 2
    - Boyd: The mechanism that detects inner-loop failure and triggers outer-loop iteration
    - Powell: Bₜ (belief state) drift detector that routes to higher modeling tiers
    - SOFAI: The Meta-Cognitive module (arxiv:2110.01834)
    """

    # TRM types whose decisions have a quantity adjustment we can measure
    QUANTITATIVE_TRM_TYPES = [
        "atp_executor", "po_creation", "inventory_rebalancing",
        "inventory_buffer", "mo_execution", "to_execution",
        "forecast_adjustment", "subcontracting",
    ]

    # TRM types with categorical decisions (harder to measure direction)
    CATEGORICAL_TRM_TYPES = [
        "order_tracking", "quality_disposition", "maintenance_scheduling",
    ]

    def __init__(
        self,
        db: Session,
        tenant_id: int,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.db = db
        self.tenant_id = tenant_id

        # Allow per-tenant threshold overrides
        cfg = config or {}
        self.persistence_window_hours = cfg.get(
            "persistence_window_hours", PERSISTENCE_WINDOW_HOURS
        )
        self.consistency_threshold = cfg.get(
            "consistency_threshold", CONSISTENCY_THRESHOLD
        )
        self.magnitude_threshold_operational = cfg.get(
            "magnitude_threshold_operational", MAGNITUDE_THRESHOLD_OPERATIONAL
        )
        self.magnitude_threshold_strategic = cfg.get(
            "magnitude_threshold_strategic", MAGNITUDE_THRESHOLD_STRATEGIC
        )
        self.cross_site_fraction = cfg.get(
            "cross_site_fraction", CROSS_SITE_FRACTION
        )
        self.min_decisions = cfg.get(
            "min_decisions_for_signal", MIN_DECISIONS_FOR_SIGNAL
        )
        self.cooldown_operational_hours = cfg.get(
            "cooldown_operational_hours", COOLDOWN_OPERATIONAL_HOURS
        )
        self.cooldown_strategic_hours = cfg.get(
            "cooldown_strategic_hours", COOLDOWN_STRATEGIC_HOURS
        )

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def evaluate_all_sites(self) -> List[EscalationVerdict]:
        """Evaluate all sites for this tenant, return any escalation verdicts.

        Called every 2h by the scheduler (relearning_jobs.py).
        """
        verdicts = []

        # Get all unique site_keys with recent decisions
        site_keys = self._get_active_site_keys()
        if not site_keys:
            return verdicts

        # Collect persistence signals per site
        all_signals: Dict[str, List[PersistenceSignal]] = {}
        for site_key in site_keys:
            signals = self._collect_persistence_signals(site_key)
            if signals:
                all_signals[site_key] = signals

        if not all_signals:
            return verdicts

        # Detect cross-site patterns
        cross_site = self._detect_cross_site_pattern(all_signals)

        # Route each site's signals
        for site_key, signals in all_signals.items():
            verdict = self._route_escalation(site_key, signals, cross_site)
            if verdict.level != EscalationLevel.NONE:
                # Check cooldown before accepting
                if self._check_cooldown(site_key, verdict.level):
                    self._log_escalation(verdict)
                    verdicts.append(verdict)
                else:
                    logger.debug(
                        "Escalation suppressed by cooldown: site=%s level=%s",
                        site_key, verdict.level,
                    )

        if verdicts:
            logger.info(
                "Escalation Arbiter found %d escalation(s) for tenant %d: %s",
                len(verdicts),
                self.tenant_id,
                [(v.level, v.affected_sites) for v in verdicts],
            )

        return verdicts

    def evaluate_site(self, site_key: str) -> EscalationVerdict:
        """Evaluate a single site for escalation (on-demand use)."""
        signals = self._collect_persistence_signals(site_key)
        if not signals:
            return EscalationVerdict(
                level=EscalationLevel.NONE,
                diagnosis="No significant persistence patterns detected",
                affected_sites=[site_key],
                affected_trm_types=[],
                recommended_action="none",
                evidence={},
                urgency="low",
            )

        # For single-site eval, pass empty cross-site pattern
        cross_site = CrossSitePattern(
            affected_sites=[], fraction_of_sites=0.0,
            dominant_direction=0.0, dominant_trm_types=[],
        )
        return self._route_escalation(site_key, signals, cross_site)

    # -----------------------------------------------------------------------
    # Signal collection
    # -----------------------------------------------------------------------

    def _get_active_site_keys(self) -> List[str]:
        """Get site_keys with recent decisions for this tenant."""
        cutoff = datetime.utcnow() - timedelta(hours=self.persistence_window_hours)
        # Query powell_atp_decisions as representative table
        # (all 11 TRM types write to powell_*_decisions tables)
        result = self.db.execute(
            text("""
                SELECT DISTINCT site_id
                FROM powell_atp_decisions
                WHERE created_at > :cutoff
                UNION
                SELECT DISTINCT site_id
                FROM powell_po_decisions
                WHERE created_at > :cutoff
                UNION
                SELECT DISTINCT site_id
                FROM powell_rebalance_decisions
                WHERE created_at > :cutoff
            """),
            {"cutoff": cutoff},
        )
        return [row[0] for row in result if row[0]]

    def _collect_persistence_signals(
        self, site_key: str
    ) -> List[PersistenceSignal]:
        """Query recent TRM decisions and compute persistence statistics.

        For each (site_key, trm_type), computes:
        - direction: mean(sign(adjustment)) — [-1, +1]
        - magnitude: mean(|adjustment / baseline|) — [0, ∞)
        - consistency: max(frac_positive, frac_negative) — [0.5, 1.0]
        """
        cutoff = datetime.utcnow() - timedelta(hours=self.persistence_window_hours)
        signals = []

        # ATP decisions — adjustment = allocated_quantity - requested_quantity
        atp_signal = self._query_decision_adjustments(
            table="powell_atp_decisions",
            site_col="site_id",
            adjustment_expr="allocated_quantity - requested_quantity",
            baseline_expr="GREATEST(requested_quantity, 1)",
            site_key=site_key,
            cutoff=cutoff,
            trm_type="atp_executor",
        )
        if atp_signal:
            signals.append(atp_signal)

        # PO decisions — adjustment = recommended_quantity - reorder_point_quantity
        po_signal = self._query_decision_adjustments(
            table="powell_po_decisions",
            site_col="site_id",
            adjustment_expr="recommended_quantity - reorder_point_quantity",
            baseline_expr="GREATEST(reorder_point_quantity, 1)",
            site_key=site_key,
            cutoff=cutoff,
            trm_type="po_creation",
        )
        if po_signal:
            signals.append(po_signal)

        # Rebalance decisions — adjustment = transfer_quantity (positive = sending more)
        rebalance_signal = self._query_decision_adjustments(
            table="powell_rebalance_decisions",
            site_col="from_site_id",
            adjustment_expr="transfer_quantity",
            baseline_expr="GREATEST(transfer_quantity, 1)",
            site_key=site_key,
            cutoff=cutoff,
            trm_type="inventory_rebalancing",
        )
        if rebalance_signal:
            signals.append(rebalance_signal)

        # Buffer decisions — adjustment = new_buffer - current_buffer
        buffer_signal = self._query_decision_adjustments(
            table="powell_buffer_decisions",
            site_col="site_id",
            adjustment_expr="new_safety_stock - current_safety_stock",
            baseline_expr="GREATEST(current_safety_stock, 1)",
            site_key=site_key,
            cutoff=cutoff,
            trm_type="inventory_buffer",
        )
        if buffer_signal:
            signals.append(buffer_signal)

        return signals

    def _query_decision_adjustments(
        self,
        table: str,
        site_col: str,
        adjustment_expr: str,
        baseline_expr: str,
        site_key: str,
        cutoff: datetime,
        trm_type: str,
    ) -> Optional[PersistenceSignal]:
        """Generic query to compute persistence stats from a decision table.

        Uses SQL aggregation for efficiency — avoids loading all rows into Python.
        """
        query = text(f"""
            SELECT
                COUNT(*) as decision_count,
                AVG(SIGN({adjustment_expr})) as direction,
                AVG(ABS(({adjustment_expr})::float / ({baseline_expr})::float)) as magnitude,
                SUM(CASE WHEN ({adjustment_expr}) > 0 THEN 1 ELSE 0 END)::float / GREATEST(COUNT(*), 1) as frac_positive,
                EXTRACT(EPOCH FROM (MAX(created_at) - MIN(created_at))) / 3600.0 as duration_hours
            FROM {table}
            WHERE {site_col} = :site_key
              AND created_at > :cutoff
        """)

        try:
            result = self.db.execute(
                query, {"site_key": site_key, "cutoff": cutoff}
            ).fetchone()
        except Exception as e:
            logger.warning(
                "Failed to query %s for site %s: %s", table, site_key, e
            )
            return None

        if not result or not result[0] or result[0] < self.min_decisions:
            return None

        decision_count = int(result[0])
        direction = float(result[1] or 0.0)
        magnitude = float(result[2] or 0.0)
        frac_positive = float(result[3] or 0.5)
        duration_hours = float(result[4] or 0.0)

        consistency = max(frac_positive, 1.0 - frac_positive)

        # Only return if the pattern is meaningful
        if consistency < 0.55 or magnitude < 0.05:
            return None

        return PersistenceSignal(
            site_key=site_key,
            trm_type=trm_type,
            direction=direction,
            magnitude=magnitude,
            consistency=consistency,
            duration_hours=duration_hours,
            decision_count=decision_count,
        )

    # -----------------------------------------------------------------------
    # Cross-site pattern detection
    # -----------------------------------------------------------------------

    def _detect_cross_site_pattern(
        self, all_signals: Dict[str, List[PersistenceSignal]]
    ) -> CrossSitePattern:
        """Check if similar persistence patterns appear across multiple sites.

        A cross-site pattern indicates network-wide issues requiring
        strategic-level intervention (Boyd: outer OODA loop must iterate).
        """
        total_sites = len(all_signals)
        if total_sites < 2:
            return CrossSitePattern(
                affected_sites=[], fraction_of_sites=0.0,
                dominant_direction=0.0, dominant_trm_types=[],
            )

        # Aggregate by trm_type across sites
        trm_type_directions: Dict[str, List[Tuple[str, float, float]]] = {}
        for site_key, signals in all_signals.items():
            for sig in signals:
                if sig.consistency >= self.consistency_threshold:
                    trm_type_directions.setdefault(sig.trm_type, []).append(
                        (site_key, sig.direction, sig.magnitude)
                    )

        # Find TRM types where multiple sites drift in the same direction
        affected_sites_set = set()
        dominant_trm_types = []
        overall_direction = 0.0

        for trm_type, entries in trm_type_directions.items():
            if len(entries) < 2:
                continue

            directions = [d for _, d, _ in entries]
            mean_dir = sum(directions) / len(directions)
            # Check if most sites agree on direction
            same_dir_count = sum(
                1 for d in directions if (d > 0) == (mean_dir > 0)
            )
            agreement = same_dir_count / len(directions)

            if agreement >= self.consistency_threshold:
                dominant_trm_types.append(trm_type)
                overall_direction += mean_dir
                for site_key, _, _ in entries:
                    affected_sites_set.add(site_key)

        fraction = len(affected_sites_set) / total_sites if total_sites > 0 else 0.0
        avg_direction = (
            overall_direction / len(dominant_trm_types)
            if dominant_trm_types
            else 0.0
        )

        return CrossSitePattern(
            affected_sites=list(affected_sites_set),
            fraction_of_sites=fraction,
            dominant_direction=avg_direction,
            dominant_trm_types=dominant_trm_types,
        )

    # -----------------------------------------------------------------------
    # Escalation routing
    # -----------------------------------------------------------------------

    def _route_escalation(
        self,
        site_key: str,
        signals: List[PersistenceSignal],
        cross_site: CrossSitePattern,
    ) -> EscalationVerdict:
        """Apply routing logic to determine escalation level.

        Routing table (from docs/ESCALATION_ARCHITECTURE.md Section 5.4):
        - Single TRM, short, low consistency → None
        - Single TRM, long, high consistency → Operational
        - Multiple TRMs, same site → Operational
        - Cross-site pattern (>30%) → Strategic
        """
        # Count significant signals (above thresholds)
        significant = [
            s for s in signals
            if s.consistency >= self.consistency_threshold
            and s.magnitude >= 0.10
        ]

        if not significant:
            return EscalationVerdict(
                level=EscalationLevel.NONE,
                diagnosis="No persistent anomalies above threshold",
                affected_sites=[site_key],
                affected_trm_types=[s.trm_type for s in signals],
                recommended_action="none",
                evidence={"signals": [asdict(s) for s in signals]},
                urgency="low",
            )

        # Check for strategic escalation first (cross-site)
        if (
            cross_site.fraction_of_sites >= self.cross_site_fraction
            and site_key in cross_site.affected_sites
        ):
            max_mag = max(s.magnitude for s in significant)
            return EscalationVerdict(
                level=EscalationLevel.STRATEGIC,
                diagnosis=(
                    f"Network-wide persistence detected: {len(cross_site.affected_sites)} sites "
                    f"({cross_site.fraction_of_sites:.0%}) show consistent "
                    f"{'upward' if cross_site.dominant_direction > 0 else 'downward'} drift "
                    f"in {', '.join(cross_site.dominant_trm_types)}. "
                    f"This indicates strategic policy parameters (θ) need revision. "
                    f"(Kahneman: System 1 anchoring bias across network; "
                    f"Boyd: inner OODA loop failing to converge — outer loop must iterate)"
                ),
                affected_sites=cross_site.affected_sites,
                affected_trm_types=cross_site.dominant_trm_types,
                recommended_action="sop_review",
                evidence={
                    "signals": [asdict(s) for s in significant],
                    "cross_site": asdict(cross_site),
                },
                urgency="critical" if max_mag >= self.magnitude_threshold_strategic else "high",
            )

        # Check for operational escalation (multi-TRM or high magnitude)
        high_magnitude = [
            s for s in significant
            if s.magnitude >= self.magnitude_threshold_operational
        ]

        if len(significant) >= 3 or (
            len(high_magnitude) >= 1
            and any(s.duration_hours >= 24 for s in high_magnitude)
        ):
            trm_types = list(set(s.trm_type for s in significant))
            max_sig = max(significant, key=lambda s: s.magnitude)
            return EscalationVerdict(
                level=EscalationLevel.OPERATIONAL,
                diagnosis=(
                    f"Persistent drift at {site_key}: {len(significant)} TRM type(s) "
                    f"({', '.join(trm_types)}) show consistent adjustments. "
                    f"Strongest: {max_sig.trm_type} at {max_sig.magnitude:.1%} magnitude, "
                    f"{max_sig.consistency:.0%} consistency over {max_sig.duration_hours:.0f}h. "
                    f"tGNN refresh recommended to recompute allocations with updated state. "
                    f"(Powell: Bₜ divergence detected — operational-level reframing needed)"
                ),
                affected_sites=[site_key],
                affected_trm_types=trm_types,
                recommended_action="tgnn_refresh",
                evidence={"signals": [asdict(s) for s in significant]},
                urgency="high" if max_sig.magnitude >= self.magnitude_threshold_strategic else "medium",
            )

        # Single-TRM long-duration drift → operational
        long_duration = [
            s for s in significant if s.duration_hours >= 24
        ]
        if long_duration:
            sig = max(long_duration, key=lambda s: s.magnitude)
            return EscalationVerdict(
                level=EscalationLevel.OPERATIONAL,
                diagnosis=(
                    f"Sustained drift in {sig.trm_type} at {site_key}: "
                    f"{sig.direction:+.2f} direction, {sig.magnitude:.1%} magnitude, "
                    f"{sig.consistency:.0%} consistency over {sig.duration_hours:.0f}h "
                    f"({sig.decision_count} decisions). "
                    f"(Kahneman: regression to the mean — TRM is compensating for bad policy)"
                ),
                affected_sites=[site_key],
                affected_trm_types=[sig.trm_type],
                recommended_action="tgnn_refresh",
                evidence={"signals": [asdict(s) for s in significant]},
                urgency="medium",
            )

        # Moderate signals → horizontal (existing CDC handles it)
        return EscalationVerdict(
            level=EscalationLevel.HORIZONTAL,
            diagnosis=(
                f"Moderate drift detected at {site_key}: "
                f"{len(significant)} signal(s) above threshold but within CDC scope. "
                f"Recommending TRM retrain / CDT recalibration."
            ),
            affected_sites=[site_key],
            affected_trm_types=[s.trm_type for s in significant],
            recommended_action="trm_retrain",
            evidence={"signals": [asdict(s) for s in significant]},
            urgency="low",
        )

    # -----------------------------------------------------------------------
    # Cooldown checks
    # -----------------------------------------------------------------------

    def _check_cooldown(self, site_key: str, level: str) -> bool:
        """Check if enough time has passed since the last escalation at this level."""
        if level == EscalationLevel.OPERATIONAL:
            cooldown_hours = self.cooldown_operational_hours
        elif level == EscalationLevel.STRATEGIC:
            cooldown_hours = self.cooldown_strategic_hours
        else:
            return True  # No cooldown for horizontal

        cutoff = datetime.utcnow() - timedelta(hours=cooldown_hours)
        count = (
            self.db.query(func.count(PowellEscalationLog.id))
            .filter(
                PowellEscalationLog.tenant_id == self.tenant_id,
                PowellEscalationLog.site_key == site_key,
                PowellEscalationLog.escalation_level == level,
                PowellEscalationLog.created_at > cutoff,
            )
            .scalar()
        )
        return count == 0

    # -----------------------------------------------------------------------
    # Logging
    # -----------------------------------------------------------------------

    def _log_escalation(self, verdict: EscalationVerdict) -> None:
        """Write escalation event to the audit log."""
        log_entry = PowellEscalationLog(
            tenant_id=self.tenant_id,
            site_key=verdict.affected_sites[0] if verdict.affected_sites else "unknown",
            escalation_level=verdict.level,
            diagnosis=verdict.diagnosis,
            urgency=verdict.urgency,
            recommended_action=verdict.recommended_action,
            affected_trm_types=verdict.affected_trm_types,
            affected_sites=verdict.affected_sites,
            evidence=verdict.evidence,
        )
        self.db.add(log_entry)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception("Failed to log escalation for tenant %d", self.tenant_id)

    # -----------------------------------------------------------------------
    # Resolution (called externally when escalation is resolved)
    # -----------------------------------------------------------------------

    def resolve_escalation(
        self, escalation_id: int, resolution: str
    ) -> Optional[PowellEscalationLog]:
        """Mark an escalation as resolved with the outcome description."""
        entry = (
            self.db.query(PowellEscalationLog)
            .filter(
                PowellEscalationLog.id == escalation_id,
                PowellEscalationLog.tenant_id == self.tenant_id,
            )
            .first()
        )
        if entry:
            entry.resolved = True
            entry.resolution = resolution
            entry.resolved_at = datetime.utcnow()
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()
                logger.exception("Failed to resolve escalation %d", escalation_id)
        return entry

    def get_unresolved(self) -> List[PowellEscalationLog]:
        """Get all unresolved escalation events for this tenant."""
        return (
            self.db.query(PowellEscalationLog)
            .filter(
                PowellEscalationLog.tenant_id == self.tenant_id,
                PowellEscalationLog.resolved == False,
            )
            .order_by(PowellEscalationLog.created_at.desc())
            .all()
        )
