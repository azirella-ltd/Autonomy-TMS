"""Forecast pipeline service with native DB adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import logging
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import sync_session_factory
from app.models.forecast_pipeline import (
    ForecastPipelineRun,
    ForecastPipelineConfig,
    ForecastPipelineCluster,
    ForecastPipelinePrediction,
    ForecastPipelineMetric,
    ForecastPipelineFeatureImportance,
    ForecastPipelinePublishLog,
)
from app.models.sc_entities import Forecast, OutboundOrderLine

logger = logging.getLogger(__name__)


@dataclass
class SeriesForecast:
    product_id: str
    site_id: str
    cluster_id: int
    forecast_date: date
    p10: float
    p50: float
    median: float
    p90: float


class ForecastPipelineService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def run_pipeline_task(run_id: int) -> None:
        """Background-task friendly wrapper with its own DB session."""
        db = sync_session_factory()
        try:
            ForecastPipelineService(db).run_pipeline(run_id)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Forecast pipeline run failed")
        finally:
            db.close()

    def run_pipeline(self, run_id: int) -> ForecastPipelineRun:
        run = self.db.query(ForecastPipelineRun).filter(ForecastPipelineRun.id == run_id).first()
        if not run:
            raise ValueError(f"Forecast pipeline run {run_id} not found")

        cfg = self.db.query(ForecastPipelineConfig).filter(ForecastPipelineConfig.id == run.pipeline_config_id).first()
        if not cfg:
            raise ValueError(f"Pipeline config {run.pipeline_config_id} not found")

        run.status = "running"
        run.started_at = datetime.utcnow()
        run.error_message = None
        self.db.flush()

        try:
            history = self._load_history(cfg)
            if history.empty:
                raise ValueError("No historical demand data available for selected config")

            history["unique_id"] = history["product_id"].astype(str) + "|" + history["site_id"].astype(str)
            history = self._filter_by_quality(history, cfg)
            if history.empty:
                raise ValueError("All series filtered out by data quality thresholds")

            clusters = self._cluster_series(history, cfg)
            forecasts = self._predict_future(history, clusters, cfg)
            metrics = self._compute_metrics(history, clusters)
            feature_scores = self._feature_scores(history, cfg)

            self.db.query(ForecastPipelineCluster).filter(ForecastPipelineCluster.run_id == run.id).delete()
            self.db.query(ForecastPipelinePrediction).filter(ForecastPipelinePrediction.run_id == run.id).delete()
            self.db.query(ForecastPipelineMetric).filter(ForecastPipelineMetric.run_id == run.id).delete()
            self.db.query(ForecastPipelineFeatureImportance).filter(
                ForecastPipelineFeatureImportance.run_id == run.id
            ).delete()

            for unique_id, cluster_id in clusters.items():
                product_id, site_id = unique_id.split("|", 1)
                self.db.add(
                    ForecastPipelineCluster(
                        run_id=run.id,
                        unique_id=unique_id,
                        product_id=product_id,
                        site_id=site_id,
                        cluster_id=cluster_id,
                    )
                )

            for row in forecasts:
                self.db.add(
                    ForecastPipelinePrediction(
                        run_id=run.id,
                        product_id=row.product_id,
                        site_id=row.site_id,
                        forecast_date=row.forecast_date,
                        cluster_id=row.cluster_id,
                        model_name=run.model_type,
                        model_version="v1",
                        forecast_p10=row.p10,
                        forecast_p50=row.p50,
                        forecast_median=row.median,
                        forecast_p90=row.p90,
                    )
                )

            for metric in metrics:
                self.db.add(ForecastPipelineMetric(run_id=run.id, **metric))

            for rank, (feature_name, score) in enumerate(feature_scores, start=1):
                self.db.add(
                    ForecastPipelineFeatureImportance(
                        run_id=run.id,
                        feature_name=feature_name,
                        importance_score=score,
                        rank=rank,
                    )
                )

            run.status = "completed"
            run.completed_at = datetime.utcnow()
            run.records_processed = len(forecasts)
            run.run_log = {
                "series_count": len(clusters),
                "forecast_rows": len(forecasts),
                "metric_rows": len(metrics),
            }
            self.db.flush()
            return run

        except Exception as exc:
            run.status = "failed"
            run.completed_at = datetime.utcnow()
            run.error_message = str(exc)
            self.db.flush()
            raise

    def publish_run(self, run_id: int, published_by_id: int, notes: str | None = None) -> int:
        run = self.db.query(ForecastPipelineRun).filter(ForecastPipelineRun.id == run_id).first()
        if not run:
            raise ValueError(f"Run {run_id} not found")
        if run.status not in {"completed", "published"}:
            raise ValueError("Only completed runs can be published")

        predictions = (
            self.db.query(ForecastPipelinePrediction)
            .filter(
                ForecastPipelinePrediction.run_id == run_id,
                ForecastPipelinePrediction.is_published.is_(False),
            )
            .all()
        )

        now = datetime.utcnow()
        published_count = 0

        for pred in predictions:
            site_id = int(pred.site_id) if str(pred.site_id).isdigit() else None
            existing = (
                self.db.query(Forecast)
                .filter(
                    Forecast.product_id == str(pred.product_id),
                    Forecast.site_id == site_id,
                    Forecast.forecast_date == pred.forecast_date,
                    Forecast.config_id == run.config_id,
                )
                .first()
            )

            if existing:
                existing.forecast_p10 = pred.forecast_p10
                existing.forecast_p50 = pred.forecast_p50
                existing.forecast_median = pred.forecast_median if pred.forecast_median is not None else pred.forecast_p50
                existing.forecast_p90 = pred.forecast_p90
                existing.forecast_quantity = pred.forecast_p50
                existing.forecast_type = "statistical"
                existing.forecast_method = "forecast_pipeline"
                existing.source = "forecast_pipeline"
                existing.source_event_id = str(run.id)
                existing.source_update_dttm = now
                existing.is_active = "true"
            else:
                self.db.add(
                    Forecast(
                        product_id=str(pred.product_id),
                        site_id=site_id,
                        forecast_date=pred.forecast_date,
                        forecast_quantity=pred.forecast_p50,
                        forecast_p10=pred.forecast_p10,
                        forecast_p50=pred.forecast_p50,
                        forecast_median=pred.forecast_median if pred.forecast_median is not None else pred.forecast_p50,
                        forecast_p90=pred.forecast_p90,
                        forecast_type="statistical",
                        forecast_level="product",
                        forecast_method="forecast_pipeline",
                        source="forecast_pipeline",
                        source_event_id=str(run.id),
                        source_update_dttm=now,
                        created_dttm=now,
                        created_by=str(published_by_id),
                        config_id=run.config_id,
                        is_active="true",
                    )
                )

            pred.is_published = True
            pred.published_at = now
            published_count += 1

        self.db.add(
            ForecastPipelinePublishLog(
                run_id=run.id,
                published_by_id=published_by_id,
                published_at=now,
                records_published=published_count,
                notes=notes,
            )
        )
        run.status = "published"
        return published_count

    def _load_history(self, cfg: ForecastPipelineConfig) -> pd.DataFrame:
        # TODO: When demand_item/demand_point/target_column/date_column are set,
        # use them as custom column mappings for the query source.
        query = (
            self.db.query(
                OutboundOrderLine.product_id.label("product_id"),
                OutboundOrderLine.site_id.label("site_id"),
                OutboundOrderLine.requested_delivery_date.label("demand_date"),
                func.sum(OutboundOrderLine.ordered_quantity).label("actual"),
            )
            .filter(OutboundOrderLine.requested_delivery_date.isnot(None))
            .group_by(
                OutboundOrderLine.product_id,
                OutboundOrderLine.site_id,
                OutboundOrderLine.requested_delivery_date,
            )
        )
        if cfg.config_id:
            query = query.filter(OutboundOrderLine.config_id == cfg.config_id)

        rows = query.all()
        if rows:
            df = pd.DataFrame(rows, columns=["product_id", "site_id", "demand_date", "actual"])
            df["demand_date"] = pd.to_datetime(df["demand_date"])
        else:
            fallback = (
                self.db.query(
                    Forecast.product_id.label("product_id"),
                    Forecast.site_id.label("site_id"),
                    Forecast.forecast_date.label("demand_date"),
                    Forecast.forecast_p50.label("actual"),
                )
                .filter(Forecast.forecast_p50.isnot(None))
            )
            if cfg.config_id:
                fallback = fallback.filter(Forecast.config_id == cfg.config_id)
            rows = fallback.all()
            df = pd.DataFrame(rows, columns=["product_id", "site_id", "demand_date", "actual"])
            if not df.empty:
                df["demand_date"] = pd.to_datetime(df["demand_date"])

        # Apply number_of_items_analyzed limit (cap unique product-site combos)
        if not df.empty and cfg.number_of_items_analyzed:
            unique_ids = df.groupby(["product_id", "site_id"]).size().reset_index(name="cnt")
            unique_ids = unique_ids.sort_values("cnt", ascending=False).head(cfg.number_of_items_analyzed)
            keep = set(zip(unique_ids["product_id"], unique_ids["site_id"]))
            df = df[df.apply(lambda r: (r["product_id"], r["site_id"]) in keep, axis=1)]

        return df

    def _filter_by_quality(self, history: pd.DataFrame, cfg: ForecastPipelineConfig) -> pd.DataFrame:
        """Filter out series that don't meet data quality thresholds."""
        if history.empty:
            return history

        stats = history.groupby("unique_id")["actual"].agg(["mean", "std", "count"])

        # Filter by minimum observations
        min_obs = int(cfg.min_observations or 12)
        keep = stats[stats["count"] >= min_obs].index

        # TODO: Apply cv_sq_threshold (coefficient of variation squared) and
        # adi_threshold (average demand interval) for demand classification
        # into smooth/erratic/intermittent/lumpy categories.
        # cv_sq = (std/mean)**2; adi = 1/non_zero_fraction
        # For now these thresholds are stored on the config for future use.

        filtered = history[history["unique_id"].isin(keep)]
        dropped = len(stats) - len(keep)
        if dropped > 0:
            logger.info("Filtered out %d series below min_observations=%d", dropped, min_obs)
        return filtered

    def _cluster_series(self, history: pd.DataFrame, cfg: ForecastPipelineConfig) -> Dict[str, int]:
        series_stats = history.groupby("unique_id")["actual"].agg(["mean", "std", "count"]).fillna(0.0)
        if series_stats.empty:
            return {}

        n_series = len(series_stats)
        k_min = max(1, int(cfg.min_clusters or 1))
        k_max = max(k_min, int(cfg.max_clusters or k_min))
        k = max(k_min, min(k_max, n_series))
        if n_series == 1:
            k = 1

        features = series_stats[["mean", "std", "count"]].to_numpy()
        method = cfg.cluster_selection_method or "KMeans"

        if k == 1:
            labels = np.zeros(n_series, dtype=int)
        elif method == "KMeans":
            labels = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(features)
        else:
            # TODO: Implement HDBSCAN, Agglomerative, OPTICS, Birch,
            # GaussianMixture, MeanShift, Spectral, AffinityPropagation.
            # These are available in the legacy scripts at
            # backend/scripts/training/forecast_pipeline/
            logger.warning(
                "Clustering method '%s' not yet implemented; falling back to KMeans", method
            )
            labels = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(features)

        clusters = dict(zip(series_stats.index.tolist(), labels.tolist()))

        # Post-process: merge clusters smaller than min_cluster_size
        min_size = int(cfg.min_cluster_size or 5)
        if cfg.min_cluster_size_uom == "percent":
            min_size = max(1, int(n_series * min_size / 100))
        from collections import Counter
        counts = Counter(clusters.values())
        small = {c for c, cnt in counts.items() if cnt < min_size}
        if small and len(counts) - len(small) > 0:
            largest = max((c for c in counts if c not in small), key=lambda c: counts[c])
            for uid, cid in clusters.items():
                if cid in small:
                    clusters[uid] = largest

        return clusters

    def _predict_future(
        self,
        history: pd.DataFrame,
        clusters: Dict[str, int],
        cfg: ForecastPipelineConfig,
    ) -> List[SeriesForecast]:
        horizon = max(1, int(cfg.forecast_horizon or 8))
        bucket = (cfg.time_bucket or "W").upper()
        forecasts: List[SeriesForecast] = []

        for unique_id, group in history.groupby("unique_id"):
            ordered = group.sort_values("demand_date")
            values = ordered["actual"].astype(float).to_numpy()
            if len(values) == 0:
                continue
            product_id = str(ordered["product_id"].iloc[0])
            site_id = str(ordered["site_id"].iloc[0])
            base = float(np.mean(values[-min(4, len(values)) :]))
            delta = float(values[-1] - values[-2]) if len(values) > 1 else 0.0
            spread = float(np.std(values[-min(8, len(values)) :])) or 1.0
            last_date = pd.to_datetime(ordered["demand_date"].max()).date()

            for step in range(1, horizon + 1):
                if bucket.startswith("D"):
                    f_date = last_date + timedelta(days=step)
                elif bucket.startswith("M"):
                    f_date = (pd.Timestamp(last_date) + pd.DateOffset(months=step)).date()
                else:
                    f_date = last_date + timedelta(weeks=step)

                p50 = max(0.0, base + (0.25 * delta * step))
                median = p50
                p10 = max(0.0, p50 - 1.28 * spread)
                p90 = max(p10, p50 + 1.28 * spread)
                forecasts.append(
                    SeriesForecast(
                        product_id=product_id,
                        site_id=site_id,
                        cluster_id=clusters.get(unique_id, 0),
                        forecast_date=f_date,
                        p10=round(p10, 4),
                        p50=round(p50, 4),
                        median=round(median, 4),
                        p90=round(p90, 4),
                    )
                )
        return forecasts

    def _compute_metrics(self, history: pd.DataFrame, clusters: Dict[str, int]) -> List[dict]:
        rows: List[dict] = []
        history = history.sort_values(["unique_id", "demand_date"]).copy()
        history["pred"] = history.groupby("unique_id")["actual"].shift(1)
        eval_df = history.dropna(subset=["pred"])
        if eval_df.empty:
            return [
                {"metric_scope": "overall", "scope_key": "overall", "metric_name": "wape", "metric_value": 0.0, "sample_size": 0},
                {"metric_scope": "overall", "scope_key": "overall", "metric_name": "mae", "metric_value": 0.0, "sample_size": 0},
                {"metric_scope": "overall", "scope_key": "overall", "metric_name": "rmse", "metric_value": 0.0, "sample_size": 0},
            ]

        eval_df["abs_err"] = (eval_df["actual"] - eval_df["pred"]).abs()
        eval_df["sq_err"] = (eval_df["actual"] - eval_df["pred"]) ** 2

        def _metric_pack(scope: str, key: str, frame: pd.DataFrame) -> List[dict]:
            denom = float(frame["actual"].abs().sum()) or 1.0
            mae = float(frame["abs_err"].mean())
            rmse = float(np.sqrt(frame["sq_err"].mean()))
            wape = float(frame["abs_err"].sum() / denom)
            n = int(len(frame))
            return [
                {"metric_scope": scope, "scope_key": key, "metric_name": "wape", "metric_value": round(wape, 6), "sample_size": n},
                {"metric_scope": scope, "scope_key": key, "metric_name": "mae", "metric_value": round(mae, 6), "sample_size": n},
                {"metric_scope": scope, "scope_key": key, "metric_name": "rmse", "metric_value": round(rmse, 6), "sample_size": n},
            ]

        rows.extend(_metric_pack("overall", "overall", eval_df))

        eval_df["cluster"] = eval_df["unique_id"].map(clusters).fillna(0).astype(int)
        for cluster_id, frame in eval_df.groupby("cluster"):
            rows.extend(_metric_pack("cluster", str(cluster_id), frame))
        return rows

    def _feature_scores(self, history: pd.DataFrame, cfg: ForecastPipelineConfig) -> List[Tuple[str, float]]:
        # TODO: When characteristics_creation_method == "tsfresh", integrate
        # tsfresh feature extraction from legacy scripts. When "classifier",
        # use sklearn classifiers for feature generation. "both" combines them.
        # TODO: Apply feature_correlation_threshold for redundant feature removal.
        # TODO: Dispatch on feature_importance_method (LassoCV/RandomForest/MutualInformation).
        # TODO: Apply feature_importance_threshold, pca_variance_threshold,
        # pca_importance_threshold from cfg.
        grouped = history.groupby("unique_id")["actual"]
        mean_series = grouped.mean().fillna(0.0)
        std_series = grouped.std().fillna(0.0)
        count_series = grouped.count().fillna(0.0).astype(float)
        cv_series = (std_series / mean_series.replace(0.0, np.nan)).fillna(0.0)
        pairs = [
            ("mean_demand", float(mean_series.mean())),
            ("std_demand", float(std_series.mean())),
            ("count_obs", float(count_series.mean())),
            ("cv_demand", float(cv_series.mean())),
        ]
        pairs.sort(key=lambda x: x[1], reverse=True)
        return pairs[:5]
