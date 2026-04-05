"""
Data Drift Monitor API

REST endpoints for the long-horizon distributional shift detection service.
Provides access to drift records, aggregated alerts, and on-demand scans.

The DataDriftMonitor is the "canary in the coal mine" for model drift:
  - CDC fires reactively when a metric threshold is breached (hourly/daily)
  - DataDriftMonitor fires proactively when distributions are SHIFTING (weekly)
"""

from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.clock import config_today_sync, tenant_today_sync
from app.models.data_drift import DataDriftAlert, DataDriftRecord

router = APIRouter(prefix="/data-drift", tags=["data-drift"])


# ── Drift Status ──────────────────────────────────────────────────────────────


@router.get("/status")
def get_drift_status(
    config_id: int = Query(..., description="Supply chain config ID"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Latest drift status for a config (28/56/84-day windows, all drift types).

    Returns the most recent record per (window_days, drift_type) combination
    so the dashboard can render a 3×3 status matrix.
    """
    # Most recent record per (window_days, drift_type)
    subq = (
        db.query(
            DataDriftRecord.window_days,
            DataDriftRecord.drift_type,
            func.max(DataDriftRecord.analysis_date).label("latest_date"),
        )
        .filter(DataDriftRecord.config_id == config_id)
        .group_by(DataDriftRecord.window_days, DataDriftRecord.drift_type)
        .subquery()
    )

    records = (
        db.query(DataDriftRecord)
        .join(
            subq,
            (DataDriftRecord.config_id == config_id)
            & (DataDriftRecord.window_days == subq.c.window_days)
            & (DataDriftRecord.drift_type == subq.c.drift_type)
            & (DataDriftRecord.analysis_date == subq.c.latest_date),
        )
        .all()
    )

    if not records:
        return {
            "config_id": config_id,
            "last_scan": None,
            "overall_severity": "none",
            "drift_matrix": [],
            "summary": "No drift records found. Scan has not yet run for this config.",
        }

    # Overall severity (worst across all records)
    severity_rank = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    overall = max(records, key=lambda r: severity_rank.get(r.drift_severity or "none", 0))

    drift_matrix = [
        {
            "window_days": r.window_days,
            "drift_type": r.drift_type,
            "drift_score": r.drift_score,
            "drift_severity": r.drift_severity,
            "drift_detected": r.drift_detected,
            "psi_score": r.psi_score,
            "ks_statistic": r.ks_statistic,
            "ks_p_value": r.ks_p_value,
            "js_divergence": r.js_divergence,
            "mean_shift": r.mean_shift,
            "analysis_date": str(r.analysis_date),
        }
        for r in sorted(records, key=lambda r: (r.window_days, r.drift_type))
    ]

    latest_date = max(r.analysis_date for r in records)

    return {
        "config_id": config_id,
        "last_scan": str(latest_date),
        "overall_severity": overall.drift_severity or "none",
        "overall_drift_score": overall.drift_score,
        "drift_detected": any(r.drift_detected for r in records),
        "drift_matrix": drift_matrix,
        "unacknowledged_alerts": db.query(DataDriftAlert)
        .filter(
            DataDriftAlert.config_id == config_id,
            DataDriftAlert.acknowledged == False,  # noqa: E712
        )
        .count(),
    }


# ── Drift Records ─────────────────────────────────────────────────────────────


@router.get("/records")
def get_drift_records(
    config_id: int = Query(..., description="Supply chain config ID"),
    days: int = Query(90, description="Look-back window in days (default: 90)"),
    drift_type: Optional[str] = Query(None, description="Filter by drift type"),
    window_days: Optional[int] = Query(None, description="Filter by window size (28/56/84)"),
    severity: Optional[str] = Query(None, description="Filter by severity (low/medium/high/critical)"),
    drift_detected_only: bool = Query(False, description="Only return records where drift was detected"),
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Historical drift records for a config with flexible filtering.

    Use this to render time-series sparklines of drift scores over weeks.
    """
    cutoff = config_today_sync(config_id, db) - timedelta(days=days)
    query = db.query(DataDriftRecord).filter(
        DataDriftRecord.config_id == config_id,
        DataDriftRecord.analysis_date >= cutoff,
    )

    if drift_type:
        query = query.filter(DataDriftRecord.drift_type == drift_type)
    if window_days:
        query = query.filter(DataDriftRecord.window_days == window_days)
    if severity:
        query = query.filter(DataDriftRecord.drift_severity == severity)
    if drift_detected_only:
        query = query.filter(DataDriftRecord.drift_detected == True)  # noqa: E712

    records = (
        query.order_by(desc(DataDriftRecord.analysis_date), DataDriftRecord.drift_type)
        .limit(limit)
        .all()
    )

    return {
        "config_id": config_id,
        "days": days,
        "count": len(records),
        "records": [
            {
                "id": r.id,
                "analysis_date": str(r.analysis_date),
                "window_days": r.window_days,
                "drift_type": r.drift_type,
                "product_id": r.product_id,
                "site_id": r.site_id,
                "drift_score": r.drift_score,
                "drift_severity": r.drift_severity,
                "drift_detected": r.drift_detected,
                "psi_score": r.psi_score,
                "ks_statistic": r.ks_statistic,
                "ks_p_value": r.ks_p_value,
                "js_divergence": r.js_divergence,
                "mean_shift": r.mean_shift,
                "variance_ratio": r.variance_ratio,
                "baseline_window": f"{r.baseline_start} → {r.baseline_end}",
                "analysis_window": f"{r.window_start} → {r.window_end}",
                "escalated": r.escalated,
            }
            for r in records
        ],
    }


# ── Drift Alerts ──────────────────────────────────────────────────────────────


@router.get("/alerts")
def get_drift_alerts(
    config_id: int = Query(..., description="Supply chain config ID"),
    days: int = Query(90, description="Look-back window in days (default: 90)"),
    unacknowledged_only: bool = Query(False),
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List drift alerts, ordered newest-first. Use unacknowledged_only for worklist view."""
    cutoff = config_today_sync(config_id, db) - timedelta(days=days)
    query = db.query(DataDriftAlert).filter(
        DataDriftAlert.config_id == config_id,
        DataDriftAlert.alert_date >= cutoff,
    )
    if unacknowledged_only:
        query = query.filter(DataDriftAlert.acknowledged == False)  # noqa: E712

    alerts = query.order_by(desc(DataDriftAlert.alert_date)).limit(limit).all()

    return {
        "config_id": config_id,
        "count": len(alerts),
        "alerts": [
            {
                "id": a.id,
                "alert_date": str(a.alert_date),
                "max_drift_score": a.max_drift_score,
                "max_severity": a.max_severity,
                "affected_products": a.affected_products,
                "affected_sites": a.affected_sites,
                "dominant_drift_type": a.dominant_drift_type,
                "psi_triggered": a.psi_triggered,
                "ks_triggered": a.ks_triggered,
                "calibration_triggered": a.calibration_triggered,
                "summary": a.summary,
                "acknowledged": a.acknowledged,
                "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
                "resolution_notes": a.resolution_notes,
                "escalated": a.escalation_log_id is not None,
                "created_at": a.created_at.isoformat(),
            }
            for a in alerts
        ],
    }


@router.patch("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: int,
    resolution_notes: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Acknowledge a drift alert (marks it as reviewed)."""
    alert = db.query(DataDriftAlert).filter(DataDriftAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.acknowledged = True
    alert.acknowledged_by = current_user.id
    alert.acknowledged_at = datetime.utcnow()
    if resolution_notes:
        alert.resolution_notes = resolution_notes
    db.commit()

    return {"status": "acknowledged", "alert_id": alert_id}


# ── On-Demand Scan ────────────────────────────────────────────────────────────


@router.post("/scan")
def trigger_scan(
    config_id: int = Query(..., description="Supply chain config ID to scan"),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Trigger an immediate distributional shift scan for a specific config.

    Runs asynchronously in the background — returns immediately.
    Poll GET /data-drift/status to see results after ~10-30 seconds.
    """

    def _run_scan(cfg_id: int):
        from app.db.session import sync_session_factory
        from app.services.powell.data_drift_monitor import DataDriftMonitor

        with sync_session_factory() as scan_db:
            monitor = DataDriftMonitor(db=scan_db)
            try:
                results = monitor.scan_config(cfg_id)
                n_drift = sum(1 for r in results if r.drift_detected)
                print(
                    f"[DataDrift] Manual scan complete for config {cfg_id}: "
                    f"{len(results)} records, {n_drift} drift detected"
                )
            except Exception as exc:
                print(f"[DataDrift] Manual scan failed for config {cfg_id}: {exc}")

    background_tasks.add_task(_run_scan, config_id)

    return {
        "status": "queued",
        "config_id": config_id,
        "message": "Scan queued. Results available via GET /data-drift/status in ~30 seconds.",
    }


# ── Summary (multi-config overview) ──────────────────────────────────────────


@router.get("/summary")
def get_drift_summary(
    days: int = Query(30),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Cross-config drift summary for the current tenant's configs.

    Used by the planning cascade dashboard to show overall model health.
    """
    from sqlalchemy import text

    cutoff = tenant_today_sync(current_user.tenant_id, db) - timedelta(days=days)

    rows = db.execute(
        text("""
            SELECT
                ddr.config_id,
                COUNT(DISTINCT ddr.id)                              AS total_records,
                SUM(CASE WHEN ddr.drift_detected THEN 1 ELSE 0 END) AS drift_detected_count,
                MAX(ddr.drift_score)                                 AS max_drift_score,
                MAX(ddr.drift_severity)                              AS worst_severity,
                MAX(ddr.analysis_date)                               AS last_scan,
                COUNT(DISTINCT dda.id)
                    FILTER (WHERE dda.acknowledged = false)          AS unacked_alerts
            FROM data_drift_records ddr
            LEFT JOIN data_drift_alerts dda
                   ON dda.config_id = ddr.config_id
                  AND dda.alert_date >= :cutoff
            WHERE ddr.analysis_date >= :cutoff
            GROUP BY ddr.config_id
            ORDER BY max_drift_score DESC NULLS LAST
        """),
        {"cutoff": cutoff},
    ).fetchall()

    return {
        "days": days,
        "configs": [
            {
                "config_id": row[0],
                "total_records": row[1],
                "drift_detected_count": row[2],
                "max_drift_score": row[3],
                "worst_severity": row[4],
                "last_scan": str(row[5]) if row[5] else None,
                "unacknowledged_alerts": row[6] or 0,
            }
            for row in rows
        ],
    }
