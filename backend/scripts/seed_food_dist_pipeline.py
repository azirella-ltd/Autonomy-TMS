"""Create and run the forecast pipeline for Food Distribution (config_id=22).

Creates a ForecastPipelineConfig, runs the full pipeline (stages 1-4),
and publishes predictions to the Forecast table.

Idempotent — deletes existing pipeline config by name before re-creating.

Run inside the container:
    docker compose exec backend python scripts/seed_food_dist_pipeline.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text

from app.db.session import sync_session_factory
from app.models.forecast_pipeline import ForecastPipelineConfig, ForecastPipelineRun
from app.services.forecast_pipeline_service import ForecastPipelineService

# Dynamic lookup — no hardcoded config IDs
from scripts.food_dist_lookup import resolve_food_dist_ids as _resolve
_fd = _resolve()
CONFIG_ID = _fd["config_id"]
TENANT_ID = _fd["tenant_id"]
ADMIN_USER_ID = _fd["admin_user_id"] or 57
PIPELINE_NAME = "Food Dist - Default Pipeline"


def main() -> None:
    db = sync_session_factory()
    try:
        print(f"Setting up forecast pipeline for Food Dist (config_id={CONFIG_ID})...")

        # 1. Clean up existing pipeline config by name
        db.execute(
            text(
                "DELETE FROM forecast_pipeline_run WHERE pipeline_config_id IN "
                "(SELECT id FROM forecast_pipeline_config WHERE name=:n AND tenant_id=:t)"
            ),
            {"n": PIPELINE_NAME, "t": TENANT_ID},
        )
        db.execute(
            text("DELETE FROM forecast_pipeline_config WHERE name=:n AND tenant_id=:t"),
            {"n": PIPELINE_NAME, "t": TENANT_ID},
        )
        db.commit()
        print("  Cleaned up existing pipeline config.")

        # 2. Create pipeline config
        pipeline_cfg = ForecastPipelineConfig(
            name=PIPELINE_NAME,
            description="Default demand forecasting pipeline for Food Distribution network",
            tenant_id=TENANT_ID,
            config_id=CONFIG_ID,
            time_bucket="W",
            forecast_horizon=12,
            min_observations=8,
            min_clusters=2,
            max_clusters=5,
            cluster_selection_method="KMeans",
            characteristics_creation_method="tsfresh",
            auto_refit_on_drift=True,
            wape_drift_threshold=0.25,
            wape_relative_threshold=0.30,
            pattern_change_threshold=0.20,
            created_by_id=ADMIN_USER_ID,
        )
        db.add(pipeline_cfg)
        db.flush()
        print(f"  Created pipeline config id={pipeline_cfg.id}")

        # 3. Create run record
        run = ForecastPipelineRun(
            pipeline_config_id=pipeline_cfg.id,
            tenant_id=TENANT_ID,
            config_id=CONFIG_ID,
            status="pending",
            created_by_id=ADMIN_USER_ID,
            model_type="clustered_naive",
            forecast_metric="wape",
        )
        db.add(run)
        db.flush()
        db.commit()
        print(f"  Created run id={run.id}, status=pending")

        # 4. Execute full pipeline (force_full=True for first run)
        print("  Running pipeline (stages 1-4, force_full=True)...")
        service = ForecastPipelineService(db)
        service.run_pipeline(run.id, force_full=True)
        db.commit()

        # Re-query to get updated status
        run = db.query(ForecastPipelineRun).filter(ForecastPipelineRun.id == run.id).first()
        print(f"  Pipeline run complete:")
        print(f"    status          = {run.status}")
        print(f"    stages_executed = {run.stages_executed}")
        print(f"    records         = {run.records_processed}")
        print(f"    drift_detected  = {run.drift_detected}")
        print(f"    drift_reason    = {run.drift_reason or 'none'}")
        print(f"    wape_current    = {run.drift_wape_current}")

        if run.status == "failed":
            print(f"  ERROR: {run.error_message}")
            sys.exit(1)

        # 5. Publish predictions to Forecast table
        print("  Publishing predictions to Forecast table...")
        published = service.publish_run(run.id, ADMIN_USER_ID, notes="Initial seed from seed_food_dist_pipeline.py")
        db.commit()
        print(f"  Published {published} forecast records.")

        print("\nFood Dist pipeline complete.")
        print(f"Run the Executive Dashboard to see ROI and forecast accuracy metrics.")

    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
