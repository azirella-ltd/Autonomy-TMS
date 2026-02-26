"""
Decision Memory Service — RAG retrieval and embedding for past decisions.

Provides two main operations:
  1. embed_decision() — Store a new decision with its state embedding
  2. find_similar_decisions() — Retrieve similar past decisions for few-shot context

Uses the same embedding infrastructure as the knowledge base (nomic-embed-text,
768 dimensions, pgvector cosine similarity).

Cost reduction strategy:
  - Cache hits (exact or near-exact match, similarity > 0.95): Return directly, no LLM call
  - Few-shot hits (similarity > 0.7): Inject as examples, use cheaper Haiku model
  - No match: Full skill prompt to Sonnet model
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class DecisionMemoryService:
    """Manages the decision embedding store for RAG retrieval."""

    # Similarity thresholds
    CACHE_HIT_THRESHOLD = 0.95  # Near-exact match, skip LLM
    FEW_SHOT_THRESHOLD = 0.70   # Good match, use as example

    def __init__(self, db: AsyncSession, embedding_service=None):
        self.db = db
        self._embedding_service = embedding_service

    async def _get_embedding_service(self):
        """Lazy-load embedding service."""
        if self._embedding_service is None:
            from app.services.embedding_service import EmbeddingService
            self._embedding_service = EmbeddingService()
        return self._embedding_service

    async def embed_decision(
        self,
        trm_type: str,
        state_features: dict[str, Any],
        state_summary: str,
        decision: dict[str, Any],
        decision_source: str = "skill",
        confidence: Optional[float] = None,
        site_key: Optional[str] = None,
        tenant_id: Optional[int] = None,
    ) -> int:
        """Store a new decision with its state embedding.

        Args:
            trm_type: TRM type identifier (e.g., "atp_executor")
            state_features: Full state features dict
            state_summary: Human-readable state summary (used for embedding)
            decision: The decision dict
            decision_source: Source of decision ("engine", "trm", "skill", "human_override")
            confidence: Decision confidence score
            site_key: Site identifier
            tenant_id: Tenant identifier

        Returns:
            ID of the created decision embedding record.
        """
        from app.models.decision_embeddings import DecisionEmbedding

        emb_svc = await self._get_embedding_service()
        try:
            embedding = await emb_svc.embed_query(state_summary)
        except Exception as e:
            logger.warning("Failed to generate embedding (non-fatal): %s", e)
            embedding = None

        record = DecisionEmbedding(
            trm_type=trm_type,
            site_key=site_key,
            tenant_id=tenant_id,
            state_features=state_features,
            state_summary=state_summary,
            decision=decision,
            decision_source=decision_source,
            confidence=confidence,
            embedding=embedding,
        )
        self.db.add(record)
        await self.db.flush()
        return record.id

    async def record_outcome(
        self,
        decision_id: int,
        outcome: dict[str, Any],
        outcome_summary: str,
        reward: float,
    ) -> None:
        """Record the outcome for a previously stored decision.

        Called by the outcome collector after the feedback horizon has elapsed.
        """
        from app.models.decision_embeddings import DecisionEmbedding

        stmt = (
            select(DecisionEmbedding)
            .where(DecisionEmbedding.id == decision_id)
        )
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()
        if record:
            record.outcome = outcome
            record.outcome_summary = outcome_summary
            record.reward = reward
            record.outcome_recorded_at = datetime.utcnow()
            await self.db.flush()

    async def find_similar_decisions(
        self,
        trm_type: str,
        state_description: str,
        top_k: int = 3,
        min_reward: float = 0.5,
        site_key: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Find similar past decisions using vector similarity search.

        Args:
            trm_type: Filter by TRM type
            state_description: Current state description to embed and search for
            top_k: Number of results to return
            min_reward: Minimum reward threshold (only return good decisions)
            site_key: Optional site filter

        Returns:
            List of similar decision dicts with similarity scores.
        """
        emb_svc = await self._get_embedding_service()
        try:
            query_embedding = await emb_svc.embed_query(state_description)
        except Exception as e:
            logger.warning("Failed to embed query for RAG lookup: %s", e)
            return []

        # pgvector cosine similarity search
        # 1 - cosine_distance gives similarity (0 to 1, higher = more similar)
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        sql = text("""
            SELECT
                id, trm_type, state_summary, decision, outcome_summary, reward,
                confidence, decision_source,
                1 - (embedding <=> :embedding::vector) AS similarity
            FROM decision_embeddings
            WHERE trm_type = :trm_type
              AND embedding IS NOT NULL
              AND outcome IS NOT NULL
              AND (reward >= :min_reward OR reward IS NULL)
              AND (:site_key IS NULL OR site_key = :site_key)
            ORDER BY embedding <=> :embedding::vector
            LIMIT :top_k
        """)

        try:
            result = await self.db.execute(sql, {
                "embedding": embedding_str,
                "trm_type": trm_type,
                "min_reward": min_reward,
                "site_key": site_key,
                "top_k": top_k,
            })
            rows = result.fetchall()
        except Exception as e:
            logger.warning("Decision memory search failed (non-fatal): %s", e)
            return []

        return [
            {
                "id": row.id,
                "trm_type": row.trm_type,
                "state_summary": row.state_summary,
                "decision": row.decision,
                "outcome_summary": row.outcome_summary,
                "reward": row.reward,
                "confidence": row.confidence,
                "decision_source": row.decision_source,
                "similarity": round(float(row.similarity), 4),
            }
            for row in rows
        ]

    async def is_cache_hit(
        self,
        trm_type: str,
        state_description: str,
        site_key: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Check if there's a near-exact match in the decision cache.

        Returns the cached decision if similarity > CACHE_HIT_THRESHOLD,
        meaning we can skip the LLM call entirely.
        """
        results = await self.find_similar_decisions(
            trm_type=trm_type,
            state_description=state_description,
            top_k=1,
            min_reward=0.5,
            site_key=site_key,
        )
        if results and results[0].get("similarity", 0) >= self.CACHE_HIT_THRESHOLD:
            return results[0]
        return None

    async def backfill_from_existing(
        self,
        trm_type: str,
        decisions_table: str,
        limit: int = 1000,
    ) -> int:
        """Backfill decision embeddings from existing powell_*_decisions tables.

        Used for cold-start: seeds the decision memory from historical decisions
        that already have outcomes recorded.

        Args:
            trm_type: TRM type identifier
            decisions_table: Name of the powell decisions table
            limit: Max records to backfill

        Returns:
            Number of decisions embedded.
        """
        # Query existing decisions with outcomes
        sql = text(f"""
            SELECT id, state_features, deterministic_result, trm_adjustment,
                   actual_outcome, reward, site_key, created_at
            FROM {decisions_table}
            WHERE actual_outcome IS NOT NULL
            ORDER BY created_at DESC
            LIMIT :limit
        """)

        try:
            result = await self.db.execute(sql, {"limit": limit})
            rows = result.fetchall()
        except Exception as e:
            logger.warning("Backfill query failed for %s: %s", decisions_table, e)
            return 0

        count = 0
        emb_svc = await self._get_embedding_service()

        for row in rows:
            state_features = row.state_features or {}
            state_summary = json.dumps(state_features, default=str)[:500]
            decision = row.trm_adjustment or row.deterministic_result or {}
            outcome = row.actual_outcome or {}
            reward = row.reward

            try:
                embedding = await emb_svc.embed_query(state_summary)
            except Exception:
                continue

            from app.models.decision_embeddings import DecisionEmbedding

            record = DecisionEmbedding(
                trm_type=trm_type,
                site_key=row.site_key if hasattr(row, "site_key") else None,
                state_features=state_features,
                state_summary=state_summary,
                decision=decision,
                decision_source="backfill",
                confidence=None,
                outcome=outcome,
                outcome_summary=json.dumps(outcome, default=str)[:500],
                reward=reward,
                embedding=embedding,
                outcome_recorded_at=datetime.utcnow(),
            )
            self.db.add(record)
            count += 1

        await self.db.flush()
        logger.info("Backfilled %d decisions from %s", count, decisions_table)
        return count
