"""
Data Drift Monitor — "Canary in the Coal Mine"

Long-horizon distributional shift detection for supply chain forecasting models.

Design philosophy
─────────────────
CDC (cdc_monitor.py) is reactive: it fires when a metric crosses a threshold
*right now* (hourly/daily cadence). That's the smoke alarm.

DataDriftMonitor is proactive: it tracks whether the *distribution* of demand,
forecast errors, and model calibration has been slowly shifting over 4–12 weeks.
That's the canary. A rising PSI score is a warning that model degradation is
coming, even if no individual metric has crossed a threshold yet.

Statistical toolkit
────────────────────
- PSI  (Population Stability Index): industry gold standard from credit risk
  monitoring. Catches shape + mass shifts, symmetric in interpretation.
    < 0.10  → no significant change (stable)
    0.10–0.20 → moderate change (watch)
    0.20–0.25 → significant change (investigate)
    > 0.25  → major change (action required)

- KS test: non-parametric H₀ test for distribution equality.
    p < 0.05 → distributions are statistically different

- Jensen-Shannon divergence: symmetric [0,1] similarity measure.
    > 0.3   → distributions meaningfully diverged

- Mean-shift / variance-ratio: interpretable moment statistics.

Drift types monitored
──────────────────────
1. "demand"         — shift in ordered_quantity distribution (input drift)
2. "forecast_error" — shift in (forecast_p50 - actual) residuals (model output drift)
3. "calibration"    — shift in prediction interval width (p90-p10) (uncertainty drift)

Analysis windows
─────────────────
28 days  (4w) — early canary: catches rapid onset shift
56 days  (8w) — main alarm: balances sensitivity and noise
84 days (12w) — trend / seasonal shift over a quarter

Integration with CDC and Escalation Arbiter
────────────────────────────────────────────
HIGH or CRITICAL drift → creates PowellEscalationLog entry
  escalation_level = "strategic" (model drift is a strategic concern)
  recommended_action = "sop_review" (S&OP to review demand model assumptions)

The Escalation Arbiter's weekly job picks these up for model retraining
recommendation (similar to how VERTICAL_STRATEGIC escalations work).

Scheduling: weekly, Sunday 03:30 UTC (before weekly planning cycle starts).
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import stats
from sqlalchemy import and_, func, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ── Configuration ──────────────────────────────────────────────────────────────

@dataclass
class DriftConfig:
    """Configurable thresholds for the drift monitor."""
    # PSI bands
    psi_watch: float = 0.10
    psi_investigate: float = 0.20
    psi_action: float = 0.25

    # KS p-value
    ks_significance: float = 0.05

    # JS divergence
    js_alert: float = 0.30

    # Mean-shift (in std devs)
    mean_shift_alert: float = 1.0

    # Composite score thresholds → severity
    score_low: float = 0.25
    score_medium: float = 0.45
    score_high: float = 0.65
    score_critical: float = 0.82

    # PSI histogram bins
    n_bins: int = 10

    # Min samples required to run a test (too few → unreliable)
    min_baseline_n: int = 14
    min_window_n: int = 7

    # Baseline = first N days of data
    baseline_days: int = 56  # 8 weeks

    # Escalation: severity levels that trigger PowellEscalationLog
    escalate_above: str = "high"  # "high" or "critical"


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class DriftWindow:
    days: int
    label: str  # "4w", "8w", "12w"


DRIFT_WINDOWS = [
    DriftWindow(days=28, label="4w"),
    DriftWindow(days=56, label="8w"),
    DriftWindow(days=84, label="12w"),
]

DRIFT_TYPES = ["demand", "forecast_error", "calibration"]


@dataclass
class DistStats:
    """Descriptive statistics + histogram for one distribution snapshot."""
    n: int
    mean: float
    std: float
    p10: float
    p50: float
    p90: float
    min_val: float
    max_val: float
    histogram: List[float]  # normalised bin counts
    bin_edges: List[float]

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "mean": round(self.mean, 4),
            "std": round(self.std, 4),
            "p10": round(self.p10, 4),
            "p50": round(self.p50, 4),
            "p90": round(self.p90, 4),
            "min": round(self.min_val, 4),
            "max": round(self.max_val, 4),
            "histogram": [round(v, 4) for v in self.histogram],
            "bin_edges": [round(v, 4) for v in self.bin_edges],
        }


@dataclass
class DriftMeasurement:
    """Results of one statistical test battery."""
    config_id: int
    product_id: Optional[str]
    site_id: Optional[int]
    analysis_date: date
    window_days: int
    window_start: date
    window_end: date
    baseline_start: date
    baseline_end: date
    drift_type: str

    # Statistics
    psi_score: Optional[float] = None
    ks_statistic: Optional[float] = None
    ks_p_value: Optional[float] = None
    js_divergence: Optional[float] = None
    mean_shift: Optional[float] = None
    variance_ratio: Optional[float] = None

    # Composite
    drift_score: float = 0.0
    drift_severity: str = "none"
    drift_detected: bool = False

    # Snapshots
    baseline_stats: Optional[DistStats] = None
    window_stats: Optional[DistStats] = None

    # Extra context
    metrics: dict = field(default_factory=dict)
    insufficient_data: bool = False


# ── Core Monitor ───────────────────────────────────────────────────────────────

class DataDriftMonitor:
    """
    Weekly data drift scanner for all active supply chain configurations.

    Entry points
    ─────────────
    scan_all_configs()          Called by the weekly APScheduler job.
    scan_config(config_id)      Called on-demand via the REST API.
    get_latest_status(config_id)  Called by dashboard endpoints.
    """

    def __init__(self, db: Session, config: Optional[DriftConfig] = None):
        self.db = db
        self.cfg = config or DriftConfig()

    # ── Public API ──────────────────────────────────────────────────────────

    def scan_all_configs(self) -> Dict[int, List[DriftMeasurement]]:
        """Weekly entry point: scan all active SC configs."""
        from app.models.supply_chain_config import SupplyChainConfig

        configs = (
            self.db.query(SupplyChainConfig)
            .filter(SupplyChainConfig.is_active == "true")
            .all()
        )
        results: Dict[int, List[DriftMeasurement]] = {}
        for cfg in configs:
            try:
                measurements = self.scan_config(cfg.id)
                results[cfg.id] = measurements
                logger.info(
                    "DataDriftMonitor: config %d — %d measurements, "
                    "%d drift detected",
                    cfg.id,
                    len(measurements),
                    sum(1 for m in measurements if m.drift_detected),
                )
            except Exception:
                logger.exception("DataDriftMonitor: config %d scan failed", cfg.id)
                results[cfg.id] = []
        return results

    def scan_config(self, config_id: int) -> List[DriftMeasurement]:
        """
        Full drift scan for one supply chain configuration.

        Iterates over all (product, site) pairs for the config, runs
        all drift type × time window combinations, persists to DB, and
        fires escalation if warranted.
        """
        from app.models.sc_entities import Product, InvPolicy
        from app.models.supply_chain_config import Site

        # Only scan products that are seeded for SC execution (have InvPolicy)
        products = (
            self.db.query(Product)
            .join(InvPolicy, InvPolicy.product_id == Product.id)
            .filter(Product.config_id == config_id)
            .all()
        )
        sites = (
            self.db.query(Site)
            .filter(Site.config_id == config_id)
            .all()
        )

        all_measurements: List[DriftMeasurement] = []
        today = date.today()

        for product in products:
            for site in sites:
                for window in DRIFT_WINDOWS:
                    for drift_type in DRIFT_TYPES:
                        m = self._measure(
                            config_id=config_id,
                            product_id=product.id,
                            site_id=site.id,
                            analysis_date=today,
                            window=window,
                            drift_type=drift_type,
                        )
                        if m is not None:
                            all_measurements.append(m)
                            self._persist(m)

        # Aggregate into one alert per config if action-level drift found
        self._maybe_raise_alert(config_id, all_measurements, today)

        self.db.commit()
        return all_measurements

    def get_latest_status(self, config_id: int) -> dict:
        """Dashboard summary: latest drift state per config."""
        from app.models.data_drift import DataDriftRecord, DataDriftAlert

        # Most recent record per drift_type × window_days
        latest_records = (
            self.db.query(DataDriftRecord)
            .filter(DataDriftRecord.config_id == config_id)
            .order_by(DataDriftRecord.analysis_date.desc())
            .limit(200)
            .all()
        )

        # Unacknowledged alerts
        open_alerts = (
            self.db.query(DataDriftAlert)
            .filter(
                DataDriftAlert.config_id == config_id,
                DataDriftAlert.acknowledged.is_(False),
            )
            .order_by(DataDriftAlert.alert_date.desc())
            .limit(10)
            .all()
        )

        if not latest_records:
            return {
                "config_id": config_id,
                "status": "no_data",
                "last_scan": None,
                "open_alerts": 0,
            }

        max_score = max((r.drift_score or 0.0) for r in latest_records)
        worst_severity = self._worst_severity(latest_records)
        by_type = {}
        for r in latest_records:
            key = f"{r.drift_type}_{r.window_days}d"
            if key not in by_type or (r.analysis_date > by_type[key]["date"]):
                by_type[key] = {
                    "date": r.analysis_date,
                    "psi": r.psi_score,
                    "drift_score": r.drift_score,
                    "severity": r.drift_severity,
                    "detected": r.drift_detected,
                }

        return {
            "config_id": config_id,
            "status": worst_severity,
            "last_scan": latest_records[0].analysis_date.isoformat(),
            "max_drift_score": round(max_score, 3),
            "worst_severity": worst_severity,
            "open_alerts": len(open_alerts),
            "by_type": {
                k: {kk: (str(v) if isinstance(v, date) else v)
                    for kk, v in vv.items()}
                for k, vv in by_type.items()
            },
        }

    # ── Measurement pipeline ────────────────────────────────────────────────

    def _measure(
        self,
        config_id: int,
        product_id: str,
        site_id: int,
        analysis_date: date,
        window: DriftWindow,
        drift_type: str,
    ) -> Optional[DriftMeasurement]:
        """
        Compute one drift measurement for a (product, site, window, type) combo.
        Returns None if insufficient data.
        """
        window_end = analysis_date
        window_start = analysis_date - timedelta(days=window.days)
        baseline_end = window_start - timedelta(days=1)
        baseline_start = baseline_end - timedelta(days=self.cfg.baseline_days)

        # Load data arrays
        if drift_type == "demand":
            baseline = self._load_demand(
                config_id, product_id, site_id, baseline_start, baseline_end
            )
            window_data = self._load_demand(
                config_id, product_id, site_id, window_start, window_end
            )
        elif drift_type == "forecast_error":
            baseline = self._load_forecast_errors(
                config_id, product_id, site_id, baseline_start, baseline_end
            )
            window_data = self._load_forecast_errors(
                config_id, product_id, site_id, window_start, window_end
            )
        elif drift_type == "calibration":
            baseline = self._load_interval_widths(
                config_id, product_id, site_id, baseline_start, baseline_end
            )
            window_data = self._load_interval_widths(
                config_id, product_id, site_id, window_start, window_end
            )
        else:
            return None

        m = DriftMeasurement(
            config_id=config_id,
            product_id=product_id,
            site_id=site_id,
            analysis_date=analysis_date,
            window_days=window.days,
            window_start=window_start,
            window_end=window_end,
            baseline_start=baseline_start,
            baseline_end=baseline_end,
            drift_type=drift_type,
        )

        if (len(baseline) < self.cfg.min_baseline_n
                or len(window_data) < self.cfg.min_window_n):
            m.insufficient_data = True
            return m

        # Run tests
        m.baseline_stats = self._dist_stats(baseline)
        m.window_stats = self._dist_stats(window_data)

        m.psi_score = self._psi(baseline, window_data)
        m.ks_statistic, m.ks_p_value = self._ks_test(baseline, window_data)
        m.js_divergence = self._js_divergence(baseline, window_data)
        m.mean_shift, m.variance_ratio = self._moment_shift(baseline, window_data)

        # Composite score and severity
        m.drift_score = self._composite_score(m)
        m.drift_severity = self._severity(m.drift_score)
        m.drift_detected = m.drift_severity not in ("none",)

        m.metrics = {
            "window_label": window.label,
            "psi_band": self._psi_band(m.psi_score),
            "ks_significant": (m.ks_p_value is not None
                               and m.ks_p_value < self.cfg.ks_significance),
            "js_alert": (m.js_divergence is not None
                         and m.js_divergence > self.cfg.js_alert),
            "mean_shift_alert": (m.mean_shift is not None
                                 and abs(m.mean_shift) > self.cfg.mean_shift_alert),
        }

        return m

    # ── Data loaders ────────────────────────────────────────────────────────

    def _load_demand(
        self,
        config_id: int,
        product_id: str,
        site_id: int,
        start: date,
        end: date,
    ) -> np.ndarray:
        """
        Load actual demand values from outbound_order_line.

        Uses weekly aggregated demand (sum per ISO week) to match the
        forecasting cadence and reduce noise from within-week spikes.
        """
        from app.models.sc_entities import OutboundOrderLine

        rows = (
            self.db.query(
                func.date_trunc("week", OutboundOrderLine.order_date).label("week"),
                func.sum(OutboundOrderLine.ordered_quantity).label("qty"),
            )
            .filter(
                OutboundOrderLine.product_id == product_id,
                OutboundOrderLine.site_id == site_id,
                OutboundOrderLine.order_date >= start,
                OutboundOrderLine.order_date <= end,
            )
            .group_by(text("week"))
            .all()
        )
        return np.array([float(r.qty) for r in rows if r.qty is not None],
                        dtype=float)

    def _load_forecast_errors(
        self,
        config_id: int,
        product_id: str,
        site_id: int,
        start: date,
        end: date,
    ) -> np.ndarray:
        """
        Load forecast residuals: forecast_p50 − actual_demand per week.

        A positive residual means we over-forecast; negative means under.
        Distribution drift here indicates the model's error pattern is changing.
        """
        from app.models.aws_sc_planning import Forecast
        from app.models.sc_entities import OutboundOrderLine

        # Weekly forecasts
        forecast_rows = (
            self.db.query(
                func.date_trunc("week", Forecast.forecast_date).label("week"),
                func.avg(Forecast.quantity).label("fcst"),
            )
            .filter(
                Forecast.product_id == product_id,
                Forecast.site_id == site_id,
                Forecast.config_id == config_id,
                Forecast.forecast_date >= start,
                Forecast.forecast_date <= end,
            )
            .group_by(text("week"))
            .all()
        )
        fcst_by_week = {r.week: float(r.fcst) for r in forecast_rows
                        if r.fcst is not None}

        # Weekly actuals
        actual_rows = (
            self.db.query(
                func.date_trunc("week", OutboundOrderLine.order_date).label("week"),
                func.sum(OutboundOrderLine.ordered_quantity).label("qty"),
            )
            .filter(
                OutboundOrderLine.product_id == product_id,
                OutboundOrderLine.site_id == site_id,
                OutboundOrderLine.order_date >= start,
                OutboundOrderLine.order_date <= end,
            )
            .group_by(text("week"))
            .all()
        )
        actual_by_week = {r.week: float(r.qty) for r in actual_rows
                          if r.qty is not None}

        # Residuals for weeks where both exist
        residuals = [
            fcst_by_week[w] - actual_by_week[w]
            for w in fcst_by_week
            if w in actual_by_week
        ]
        return np.array(residuals, dtype=float)

    def _load_interval_widths(
        self,
        config_id: int,
        product_id: str,
        site_id: int,
        start: date,
        end: date,
    ) -> np.ndarray:
        """
        Load prediction interval widths: p90 − p10 per week.

        Widening intervals over time indicate the model has become less
        certain — a key calibration drift signal.
        """
        from app.models.aws_sc_planning import Forecast

        rows = (
            self.db.query(
                func.date_trunc("week", Forecast.forecast_date).label("week"),
                func.avg(Forecast.p90_quantity - Forecast.p10_quantity).label("width"),
            )
            .filter(
                Forecast.product_id == product_id,
                Forecast.site_id == site_id,
                Forecast.config_id == config_id,
                Forecast.forecast_date >= start,
                Forecast.forecast_date <= end,
                Forecast.p90_quantity.isnot(None),
                Forecast.p10_quantity.isnot(None),
            )
            .group_by(text("week"))
            .all()
        )
        return np.array([float(r.width) for r in rows if r.width is not None],
                        dtype=float)

    # ── Statistical tests ───────────────────────────────────────────────────

    def _psi(self, baseline: np.ndarray, current: np.ndarray) -> float:
        """
        Population Stability Index.

        PSI = Σ (A_i − E_i) × ln(A_i / E_i)
        where E_i = baseline bucket proportion, A_i = current bucket proportion.

        Shared bin edges computed from the combined distribution so that both
        arrays are compared on the same scale.
        """
        eps = 1e-6
        combined = np.concatenate([baseline, current])
        bins = np.linspace(combined.min(), combined.max(), self.cfg.n_bins + 1)

        base_counts, _ = np.histogram(baseline, bins=bins)
        curr_counts, _ = np.histogram(current, bins=bins)

        base_pct = base_counts / (base_counts.sum() + eps)
        curr_pct = curr_counts / (curr_counts.sum() + eps)

        # Avoid log(0)
        base_pct = np.clip(base_pct, eps, None)
        curr_pct = np.clip(curr_pct, eps, None)

        psi = float(np.sum((curr_pct - base_pct) * np.log(curr_pct / base_pct)))
        return round(max(0.0, psi), 6)

    def _ks_test(
        self, baseline: np.ndarray, current: np.ndarray
    ) -> Tuple[float, float]:
        """Two-sample KS test. Returns (statistic, p_value)."""
        result = stats.ks_2samp(baseline, current)
        return round(float(result.statistic), 6), round(float(result.pvalue), 6)

    def _js_divergence(
        self, baseline: np.ndarray, current: np.ndarray
    ) -> float:
        """
        Jensen-Shannon divergence [0, 1].

        Computes p and q as normalised histograms on shared bins,
        then JS = (KL(p||m) + KL(q||m)) / 2  where m = (p+q)/2.
        """
        eps = 1e-6
        combined = np.concatenate([baseline, current])
        bins = np.linspace(combined.min(), combined.max(), self.cfg.n_bins + 1)

        p_counts, _ = np.histogram(baseline, bins=bins)
        q_counts, _ = np.histogram(current, bins=bins)

        p = p_counts / (p_counts.sum() + eps)
        q = q_counts / (q_counts.sum() + eps)
        p = np.clip(p, eps, None)
        q = np.clip(q, eps, None)

        m = (p + q) / 2

        def kl(a: np.ndarray, b: np.ndarray) -> float:
            return float(np.sum(a * np.log(a / b)))

        js = (kl(p, m) + kl(q, m)) / 2
        # JS divergence bounded by log(2) ≈ 0.693; normalise to [0,1]
        js_norm = js / math.log(2)
        return round(max(0.0, min(1.0, js_norm)), 6)

    def _moment_shift(
        self, baseline: np.ndarray, current: np.ndarray
    ) -> Tuple[float, float]:
        """Return (mean_shift_in_std_devs, variance_ratio)."""
        base_std = float(np.std(baseline)) if len(baseline) > 1 else 1.0
        if base_std < 1e-9:
            base_std = 1.0
        mean_shift = (float(np.mean(current)) - float(np.mean(baseline))) / base_std
        base_var = float(np.var(baseline)) if len(baseline) > 1 else 1.0
        curr_var = float(np.var(current)) if len(current) > 1 else 1.0
        var_ratio = curr_var / max(base_var, 1e-9)
        return round(mean_shift, 4), round(var_ratio, 4)

    def _dist_stats(self, arr: np.ndarray) -> DistStats:
        """Compute descriptive statistics + histogram for persistence."""
        n_bins = self.cfg.n_bins
        counts, edges = np.histogram(arr, bins=n_bins)
        total = counts.sum()
        hist_norm = (counts / total).tolist() if total > 0 else [0.0] * n_bins
        return DistStats(
            n=int(len(arr)),
            mean=round(float(np.mean(arr)), 4),
            std=round(float(np.std(arr)), 4),
            p10=round(float(np.percentile(arr, 10)), 4),
            p50=round(float(np.percentile(arr, 50)), 4),
            p90=round(float(np.percentile(arr, 90)), 4),
            min_val=round(float(arr.min()), 4),
            max_val=round(float(arr.max()), 4),
            histogram=hist_norm,
            bin_edges=[round(float(e), 4) for e in edges.tolist()],
        )

    # ── Scoring ─────────────────────────────────────────────────────────────

    def _composite_score(self, m: DriftMeasurement) -> float:
        """
        Weighted composite drift score [0, 1].

        Weights:
          PSI          0.50  (primary signal — most interpretable)
          KS test      0.25  (statistical significance)
          JS divergence 0.15  (shape similarity)
          Mean shift   0.10  (interpretable directionality)
        """
        score = 0.0

        # PSI component (map through PSI bands)
        if m.psi_score is not None:
            psi = m.psi_score
            if psi >= self.cfg.psi_action:
                psi_norm = min(1.0, psi / self.cfg.psi_action)
            elif psi >= self.cfg.psi_investigate:
                psi_norm = 0.65 + 0.35 * (
                    (psi - self.cfg.psi_investigate)
                    / (self.cfg.psi_action - self.cfg.psi_investigate)
                )
            elif psi >= self.cfg.psi_watch:
                psi_norm = 0.25 + 0.40 * (
                    (psi - self.cfg.psi_watch)
                    / (self.cfg.psi_investigate - self.cfg.psi_watch)
                )
            else:
                psi_norm = psi / self.cfg.psi_watch * 0.25
            score += 0.50 * psi_norm

        # KS component (p-value → penalty; low p = high drift)
        if m.ks_p_value is not None:
            # Transform: p=0 → 1.0, p=0.05 → 0.5, p=1 → 0.0
            ks_norm = max(0.0, 1.0 - (m.ks_p_value / self.cfg.ks_significance) * 0.5)
            score += 0.25 * min(1.0, ks_norm)

        # JS component
        if m.js_divergence is not None:
            js_norm = min(1.0, m.js_divergence / self.cfg.js_alert)
            score += 0.15 * js_norm

        # Mean-shift component
        if m.mean_shift is not None:
            ms_norm = min(1.0, abs(m.mean_shift) / self.cfg.mean_shift_alert)
            score += 0.10 * ms_norm

        return round(min(1.0, max(0.0, score)), 4)

    def _severity(self, score: float) -> str:
        if score >= self.cfg.score_critical:
            return "critical"
        if score >= self.cfg.score_high:
            return "high"
        if score >= self.cfg.score_medium:
            return "medium"
        if score >= self.cfg.score_low:
            return "low"
        return "none"

    def _psi_band(self, psi: Optional[float]) -> str:
        if psi is None:
            return "unknown"
        if psi >= self.cfg.psi_action:
            return "action"
        if psi >= self.cfg.psi_investigate:
            return "investigate"
        if psi >= self.cfg.psi_watch:
            return "watch"
        return "stable"

    def _worst_severity(self, records) -> str:
        order = ["none", "low", "medium", "high", "critical"]
        worst = "none"
        for r in records:
            sev = r.drift_severity or "none"
            if order.index(sev) > order.index(worst):
                worst = sev
        return worst

    # ── Persistence ─────────────────────────────────────────────────────────

    def _persist(self, m: DriftMeasurement) -> None:
        """Write or update DriftMeasurement to data_drift_records."""
        if m.insufficient_data:
            return  # Don't clutter DB with no-data records
        try:
            from app.models.data_drift import DataDriftRecord

            record = DataDriftRecord(
                config_id=m.config_id,
                product_id=m.product_id,
                site_id=m.site_id,
                analysis_date=m.analysis_date,
                baseline_start=m.baseline_start,
                baseline_end=m.baseline_end,
                window_start=m.window_start,
                window_end=m.window_end,
                window_days=m.window_days,
                drift_type=m.drift_type,
                psi_score=m.psi_score,
                ks_statistic=m.ks_statistic,
                ks_p_value=m.ks_p_value,
                js_divergence=m.js_divergence,
                mean_shift=m.mean_shift,
                variance_ratio=m.variance_ratio,
                drift_score=m.drift_score,
                drift_severity=m.drift_severity,
                drift_detected=m.drift_detected,
                baseline_stats=m.baseline_stats.to_dict() if m.baseline_stats else None,
                window_stats=m.window_stats.to_dict() if m.window_stats else None,
                metrics=m.metrics,
            )
            self.db.add(record)
            self.db.flush()
            return record.id
        except Exception:
            logger.exception(
                "DataDriftMonitor: failed to persist record for "
                "config=%d product=%s site=%s window=%dd type=%s",
                m.config_id, m.product_id, m.site_id, m.window_days, m.drift_type,
            )
            try:
                self.db.rollback()
            except Exception:
                pass

    def _maybe_raise_alert(
        self,
        config_id: int,
        measurements: List[DriftMeasurement],
        today: date,
    ) -> None:
        """
        If any measurements exceed the action threshold, create a
        DataDriftAlert and (if above escalate_above) a PowellEscalationLog.
        """
        action_measurements = [
            m for m in measurements
            if m.drift_severity in ("high", "critical") and not m.insufficient_data
        ]
        if not action_measurements:
            return

        from app.models.data_drift import DataDriftAlert

        max_score = max(m.drift_score for m in action_measurements)
        max_sev = self._worst_severity(  # type: ignore[arg-type]
            type("R", (), {"drift_severity": m.drift_severity})()
            for m in action_measurements
        )
        # Simpler approach:
        sev_order = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
        max_sev = max(action_measurements, key=lambda m: sev_order.get(m.drift_severity, 0)).drift_severity

        affected_products = len({m.product_id for m in action_measurements})
        affected_sites = len({m.site_id for m in action_measurements})

        type_counts: Dict[str, int] = {}
        for m in action_measurements:
            type_counts[m.drift_type] = type_counts.get(m.drift_type, 0) + 1
        dominant_type = max(type_counts, key=type_counts.get)  # type: ignore[arg-type]

        summary = (
            f"Data drift detected in config {config_id}: "
            f"{len(action_measurements)} measurements at {max_sev} severity. "
            f"Max drift score: {max_score:.2f}. "
            f"Dominant drift type: {dominant_type}. "
            f"Affects {affected_products} product(s) × {affected_sites} site(s)."
        )

        alert = DataDriftAlert(
            config_id=config_id,
            alert_date=today,
            max_drift_score=max_score,
            max_severity=max_sev,
            affected_products=affected_products,
            affected_sites=affected_sites,
            dominant_drift_type=dominant_type,
            psi_triggered=any(
                (m.psi_score or 0) >= self.cfg.psi_action for m in action_measurements
            ),
            ks_triggered=any(
                (m.ks_p_value or 1) < self.cfg.ks_significance for m in action_measurements
            ),
            calibration_triggered=any(
                m.drift_type == "calibration" for m in action_measurements
            ),
            summary=summary,
        )
        self.db.add(alert)
        self.db.flush()

        # Escalate to PowellEscalationLog if severity warrants it
        escalate_sevs = {"high", "critical"}
        if max_sev in escalate_sevs:
            self._escalate(config_id, action_measurements, max_sev, summary, alert)
            alert.escalated = True

        logger.warning("DataDriftMonitor: alert raised for config %d — %s", config_id, summary)

    def _escalate(
        self,
        config_id: int,
        measurements: List[DriftMeasurement],
        severity: str,
        summary: str,
        alert,
    ) -> None:
        """
        Write a PowellEscalationLog entry for model-drift-triggered escalation.

        escalation_level = "strategic"  (model drift is a long-horizon concern)
        recommended_action = "sop_review"  (S&OP should review model assumptions)

        The EscalationArbiter and CDC pipelines will see this entry in the log
        and factor it into their retraining evaluation logic.
        """
        try:
            from app.models.escalation_log import PowellEscalationLog
            from app.models.supply_chain_config import SupplyChainConfig, Site

            # Get tenant_id from config
            config_obj = (
                self.db.query(SupplyChainConfig)
                .filter(SupplyChainConfig.id == config_id)
                .first()
            )
            tenant_id = getattr(config_obj, "tenant_id", None) if config_obj else None
            if tenant_id is None:
                logger.warning(
                    "DataDriftMonitor: cannot escalate for config %d — no tenant_id",
                    config_id,
                )
                return

            affected_sites = list({
                str(m.site_id) for m in measurements if m.site_id is not None
            })

            # Build site_key from config (use config_id as namespace)
            site_key = f"config_{config_id}"

            evidence = {
                "source": "data_drift_monitor",
                "config_id": config_id,
                "max_drift_score": max(m.drift_score for m in measurements),
                "measurement_count": len(measurements),
                "drift_types": list({m.drift_type for m in measurements}),
                "window_days": list({m.window_days for m in measurements}),
                "psi_scores": [
                    {"type": m.drift_type, "window": m.window_days, "psi": m.psi_score}
                    for m in measurements if m.psi_score is not None
                ][:10],  # cap for JSON size
            }

            esc = PowellEscalationLog(
                tenant_id=tenant_id,
                site_key=site_key,
                escalation_level="strategic",
                diagnosis=(
                    f"DataDriftMonitor detected {severity} distributional shift "
                    f"in config {config_id}. " + summary
                ),
                urgency=severity,
                recommended_action="sop_review",
                affected_sites=affected_sites,
                evidence=evidence,
            )
            self.db.add(esc)
            self.db.flush()

            # Back-link the alert to this escalation
            alert.escalation_log_id = esc.id

            logger.info(
                "DataDriftMonitor: escalation log created for config %d "
                "(level=strategic, urgency=%s)",
                config_id,
                severity,
            )
        except Exception:
            logger.exception(
                "DataDriftMonitor: failed to create escalation log for config %d",
                config_id,
            )
