"""
Scheduler jobs for the unified training corpus.

- Daily: weight decay (age-based re-weighting and pruning of low-weight samples)
- Weekly: aggregator refresh (re-roll Level 1 -> 1.5, 2, 4 on new real outcomes)
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def run_corpus_weight_decay() -> Dict[str, Any]:
    """Apply exponential weight decay to all corpus samples.

    Runs daily. Samples with weight < 0.05 are pruned.
    """
    from app.db.session import async_session_factory
    from sqlalchemy import text as sql_text
    from app.services.training_corpus import TrainingCorpusService

    total_pruned = 0
    configs_processed = 0

    async with async_session_factory() as db:
        # Get all configs with corpus samples
        result = await db.execute(
            sql_text("SELECT DISTINCT config_id FROM training_corpus")
        )
        config_ids = [row.config_id for row in result.fetchall()]

        service = TrainingCorpusService(db)
        for config_id in config_ids:
            pruned = await service.compute_weights(config_id)
            total_pruned += pruned
            configs_processed += 1

    logger.info(
        "Corpus weight decay: %d configs processed, %d samples pruned",
        configs_processed, total_pruned,
    )
    return {"configs_processed": configs_processed, "samples_pruned": total_pruned}


async def run_corpus_aggregator_refresh() -> Dict[str, Any]:
    """Re-run the aggregator for configs with new real outcomes.

    Runs weekly. For each config that has new Layer 1 samples with origin='real'
    since the last aggregation, re-roll them into Layer 2, 2, 4.
    """
    from app.db.session import async_session_factory
    from sqlalchemy import text as sql_text
    from app.services.training_corpus.aggregator import TrainingCorpusAggregator

    configs_refreshed = 0
    samples_generated = {"layer2": 0, "layer2": 0, "layer4": 0}

    async with async_session_factory() as db:
        # Find configs with real outcomes added since last aggregation
        result = await db.execute(
            sql_text("""
                SELECT DISTINCT config_id, tenant_id
                FROM training_corpus
                WHERE origin = 'real'
                  AND created_at > NOW() - INTERVAL '7 days'
                  AND layer = 1.0
            """)
        )
        rows = result.fetchall()

        aggregator = TrainingCorpusAggregator(db)
        for row in rows:
            config_id = row.config_id
            tenant_id = row.tenant_id

            # Clear stale higher-layer samples (they'll be regenerated)
            await db.execute(
                sql_text("""
                    DELETE FROM training_corpus
                    WHERE config_id = :cid
                      AND layer IN (1.5, 2.0, 4.0)
                      AND origin = 'simulation'
                      AND created_at < NOW() - INTERVAL '7 days'
                """),
                {"cid": config_id},
            )

            # Re-aggregate
            try:
                summary = await aggregator.aggregate_all_levels(tenant_id, config_id)
                samples_generated["layer2"] += summary.get("layer2_count", 0)
                samples_generated["layer2"] += summary.get("layer3_count", 0)
                samples_generated["layer4"] += summary.get("layer4_count", 0)
                configs_refreshed += 1
            except Exception as e:
                logger.warning("Aggregator refresh failed for config %d: %s", config_id, e)

        await db.commit()

    logger.info(
        "Corpus aggregator refresh: %d configs refreshed, %s samples generated",
        configs_refreshed, samples_generated,
    )
    return {
        "configs_refreshed": configs_refreshed,
        "samples_generated": samples_generated,
    }


def register_corpus_jobs(scheduler_service) -> int:
    """Register corpus maintenance jobs with the APScheduler.

    Returns number of jobs registered.
    """
    try:
        # Daily weight decay at 3am
        scheduler_service.add_cron_job(
            func=run_corpus_weight_decay,
            job_id="corpus_weight_decay",
            hour=3,
            minute=0,
            replace_existing=True,
        )

        # Weekly aggregator refresh on Sunday at 4am
        scheduler_service.add_cron_job(
            func=run_corpus_aggregator_refresh,
            job_id="corpus_aggregator_refresh",
            day_of_week="sun",
            hour=4,
            minute=0,
            replace_existing=True,
        )

        logger.info("Training corpus scheduler jobs registered")
        return 2
    except Exception as e:
        logger.warning("Corpus job registration failed: %s", e)
        return 0
