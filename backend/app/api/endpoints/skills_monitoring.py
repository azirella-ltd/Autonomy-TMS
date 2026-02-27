"""
Skills Monitoring API — Stats and metrics for Claude Skills decisions.

Provides endpoints for the frontend SkillsDashboard to display:
- Escalation rates (TRM vs Skills decisions)
- Skills decision outcomes and reward distributions
- RAG cache hit rates
- Per-TRM-type breakdown
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user

router = APIRouter(prefix="/skills-monitoring", tags=["skills-monitoring"])


@router.get("/stats")
def get_skills_stats(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get aggregated skills monitoring statistics."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Total decisions by source
    source_counts = db.execute(
        text("""
            SELECT decision_source, COUNT(*) as cnt
            FROM decision_embeddings
            WHERE created_at > :cutoff
            GROUP BY decision_source
            ORDER BY cnt DESC
        """),
        {"cutoff": cutoff},
    )
    source_breakdown = {row[0]: row[1] for row in source_counts.fetchall()}

    # Per-TRM-type breakdown
    type_counts = db.execute(
        text("""
            SELECT trm_type, decision_source, COUNT(*) as cnt,
                   AVG(confidence) as avg_confidence,
                   AVG(reward) as avg_reward,
                   COUNT(CASE WHEN outcome IS NOT NULL THEN 1 END) as with_outcome
            FROM decision_embeddings
            WHERE created_at > :cutoff
            GROUP BY trm_type, decision_source
            ORDER BY trm_type, decision_source
        """),
        {"cutoff": cutoff},
    )
    type_breakdown = {}
    for row in type_counts.fetchall():
        trm_type = row[0]
        if trm_type not in type_breakdown:
            type_breakdown[trm_type] = {}
        type_breakdown[trm_type][row[1]] = {
            "count": row[2],
            "avg_confidence": round(float(row[3] or 0), 3),
            "avg_reward": round(float(row[4] or 0), 3),
            "with_outcome": row[5],
        }

    # Reward distribution for skill decisions
    reward_stats = db.execute(
        text("""
            SELECT
                COUNT(*) as total,
                AVG(reward) as avg_reward,
                MIN(reward) as min_reward,
                MAX(reward) as max_reward,
                COUNT(CASE WHEN reward > 0.5 THEN 1 END) as good,
                COUNT(CASE WHEN reward > 0 AND reward <= 0.5 THEN 1 END) as moderate,
                COUNT(CASE WHEN reward <= 0 THEN 1 END) as poor,
                COUNT(CASE WHEN reward IS NULL THEN 1 END) as pending
            FROM decision_embeddings
            WHERE created_at > :cutoff AND decision_source = 'skill_exception'
        """),
        {"cutoff": cutoff},
    )
    reward_row = reward_stats.fetchone()

    # Recent decisions (last 20)
    recent = db.execute(
        text("""
            SELECT id, trm_type, decision_source, confidence, reward,
                   state_summary, created_at, outcome_recorded_at,
                   site_key
            FROM decision_embeddings
            WHERE created_at > :cutoff
            ORDER BY created_at DESC
            LIMIT 20
        """),
        {"cutoff": cutoff},
    )
    recent_decisions = [
        {
            "id": row[0],
            "trm_type": row[1],
            "decision_source": row[2],
            "confidence": round(float(row[3] or 0), 3),
            "reward": round(float(row[4] or 0), 3) if row[4] is not None else None,
            "state_summary": (row[5] or "")[:200],
            "created_at": row[6].isoformat() if row[6] else None,
            "outcome_recorded_at": row[7].isoformat() if row[7] else None,
            "site_key": row[8],
        }
        for row in recent.fetchall()
    ]

    # Escalation rate (skill decisions / total TRM decisions)
    total_trm = db.execute(
        text("""
            SELECT COUNT(*) FROM powell_atp_decisions WHERE created_at > :cutoff
            UNION ALL
            SELECT COUNT(*) FROM powell_po_decisions WHERE created_at > :cutoff
            UNION ALL
            SELECT COUNT(*) FROM powell_rebalance_decisions WHERE created_at > :cutoff
            UNION ALL
            SELECT COUNT(*) FROM powell_order_exceptions WHERE created_at > :cutoff
        """),
        {"cutoff": cutoff},
    )
    trm_total = sum(row[0] for row in total_trm.fetchall())
    skill_total = source_breakdown.get("skill_exception", 0)
    escalation_rate = (
        round(skill_total / (trm_total + skill_total) * 100, 1)
        if (trm_total + skill_total) > 0
        else 0
    )

    return {
        "period_days": days,
        "source_breakdown": source_breakdown,
        "type_breakdown": type_breakdown,
        "escalation_rate": escalation_rate,
        "total_trm_decisions": trm_total,
        "total_skill_decisions": skill_total,
        "reward_distribution": {
            "total": reward_row[0] if reward_row else 0,
            "avg_reward": round(float(reward_row[1] or 0), 3) if reward_row else 0,
            "min_reward": round(float(reward_row[2] or 0), 3) if reward_row else 0,
            "max_reward": round(float(reward_row[3] or 0), 3) if reward_row else 0,
            "good": reward_row[4] if reward_row else 0,
            "moderate": reward_row[5] if reward_row else 0,
            "poor": reward_row[6] if reward_row else 0,
            "pending_outcome": reward_row[7] if reward_row else 0,
        },
        "recent_decisions": recent_decisions,
    }


@router.get("/rag-stats")
def get_rag_stats(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get RAG decision memory statistics."""
    # Total embeddings
    total = db.execute(
        text("SELECT COUNT(*) FROM decision_embeddings"),
    )
    total_count = total.scalar() or 0

    # With embeddings vs without
    with_embedding = db.execute(
        text("SELECT COUNT(*) FROM decision_embeddings WHERE embedding IS NOT NULL"),
    )
    embedded_count = with_embedding.scalar() or 0

    # With outcomes (useful for RAG)
    with_outcome = db.execute(
        text("""
            SELECT COUNT(*) FROM decision_embeddings
            WHERE outcome IS NOT NULL AND reward IS NOT NULL
        """),
    )
    outcome_count = with_outcome.scalar() or 0

    # High-reward decisions (>0.5) — best RAG examples
    high_reward = db.execute(
        text("""
            SELECT COUNT(*) FROM decision_embeddings
            WHERE reward > 0.5
        """),
    )
    high_reward_count = high_reward.scalar() or 0

    # By TRM type
    by_type = db.execute(
        text("""
            SELECT trm_type, COUNT(*) as total,
                   COUNT(CASE WHEN outcome IS NOT NULL THEN 1 END) as with_outcome,
                   COUNT(CASE WHEN reward > 0.5 THEN 1 END) as high_reward,
                   AVG(reward) as avg_reward
            FROM decision_embeddings
            GROUP BY trm_type
            ORDER BY total DESC
        """),
    )
    type_stats = [
        {
            "trm_type": row[0],
            "total": row[1],
            "with_outcome": row[2],
            "high_reward": row[3],
            "avg_reward": round(float(row[4] or 0), 3),
        }
        for row in by_type.fetchall()
    ]

    return {
        "total_embeddings": total_count,
        "with_embedding_vector": embedded_count,
        "with_outcome": outcome_count,
        "high_reward_examples": high_reward_count,
        "embedding_coverage": (
            round(embedded_count / total_count * 100, 1)
            if total_count > 0
            else 0
        ),
        "by_type": type_stats,
    }
