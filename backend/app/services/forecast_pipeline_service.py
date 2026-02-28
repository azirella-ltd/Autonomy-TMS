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
    ForecastPipelinePrediction,
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

            # Persist only the forecast predictions (the actionable output).
            # Clusters, metrics, and feature importance are folded into run_log
            # JSON — they were previously written to separate tables but never read.
            self.db.query(ForecastPipelinePrediction).filter(ForecastPipelinePrediction.run_id == run.id).delete()

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

            run.status = "completed"
            run.completed_at = datetime.utcnow()
            run.records_processed = len(forecasts)
            run.run_log = {
                "series_count": len(clusters),
                "forecast_rows": len(forecasts),
                "clusters": {uid: int(cid) for uid, cid in clusters.items()},
                "metrics": metrics,
                "feature_importance": [
                    {"feature": name, "score": float(score)}
                    for name, score in feature_scores
                ],
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

        filtered = history[history["unique_id"].isin(keep)]
        dropped = len(stats) - len(keep)
        if dropped > 0:
            logger.info("Filtered out %d series below min_observations=%d", dropped, min_obs)
        return filtered

    @staticmethod
    def _classify_demand(values: np.ndarray, cv_sq_thresh: float = 0.49, adi_thresh: float = 1.32) -> str:
        """Classify demand pattern using CV-squared and ADI (Syntetos-Boylan).

        Returns one of: smooth, erratic, intermittent, lumpy.
        """
        mean_val = float(np.mean(values))
        std_val = float(np.std(values))
        cv_sq = (std_val / mean_val) ** 2 if mean_val > 0 else 0.0

        non_zero = np.count_nonzero(values)
        adi = len(values) / non_zero if non_zero > 0 else float("inf")

        if cv_sq < cv_sq_thresh and adi < adi_thresh:
            return "smooth"
        elif cv_sq >= cv_sq_thresh and adi < adi_thresh:
            return "erratic"
        elif cv_sq < cv_sq_thresh and adi >= adi_thresh:
            return "intermittent"
        else:
            return "lumpy"

    @staticmethod
    def _classify_demand_robust(
        values: np.ndarray,
        cv_sq_thresh: float = 0.49,
        adi_thresh: float = 1.32,
    ) -> Tuple[str, Dict]:
        """Robust demand classification using MAD/median instead of std/mean.

        Insight: Kravanja (2026) - mean and std are outlier-sensitive. A single
        demand spike can inflate std and misclassify smooth demand as erratic.
        MAD (Median Absolute Deviation) and median are robust to outliers while
        preserving the Syntetos-Boylan classification framework.

        Returns:
            (pattern_name, metadata) where metadata includes robust stats and
            optionally the best-fit distribution type for the non-zero values.
        """
        median_val = float(np.median(values))
        mad_val = float(np.median(np.abs(values - median_val)))

        # Robust CV^2 using MAD/median (analogous to std/mean)
        # Scale MAD by 1.4826 to make it comparable to std for Normal data
        scaled_mad = mad_val * 1.4826
        robust_cv_sq = (scaled_mad / median_val) ** 2 if median_val > 0 else 0.0

        non_zero = np.count_nonzero(values)
        adi = len(values) / non_zero if non_zero > 0 else float("inf")

        metadata: Dict = {
            "median": median_val,
            "mad": mad_val,
            "scaled_mad": scaled_mad,
            "robust_cv_sq": robust_cv_sq,
            "adi": adi,
            "n": len(values),
            "pct_zeros": float(np.sum(values == 0) / len(values)) if len(values) > 0 else 0.0,
        }

        # Fit distribution to non-zero values when enough data
        non_zero_values = values[values > 0]
        if len(non_zero_values) >= 10:
            try:
                from app.services.stochastic.distribution_fitter import DistributionFitter
                fitter = DistributionFitter()
                report = fitter.fit(non_zero_values, variable_type="demand")
                metadata["fitted_dist"] = report.best.dist_type
                metadata["fitted_params"] = report.best.params
                metadata["fitted_ks_pvalue"] = report.best.ks_pvalue
            except Exception:
                pass

        if robust_cv_sq < cv_sq_thresh and adi < adi_thresh:
            return "smooth", metadata
        elif robust_cv_sq >= cv_sq_thresh and adi < adi_thresh:
            return "erratic", metadata
        elif robust_cv_sq < cv_sq_thresh and adi >= adi_thresh:
            return "intermittent", metadata
        else:
            return "lumpy", metadata

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
        elif method == "Agglomerative":
            from sklearn.cluster import AgglomerativeClustering
            labels = AgglomerativeClustering(n_clusters=k).fit_predict(features)
        elif method == "Birch":
            from sklearn.cluster import Birch
            labels = Birch(n_clusters=k).fit_predict(features)
        elif method == "GaussianMixture":
            from sklearn.mixture import GaussianMixture
            labels = GaussianMixture(n_components=k, random_state=42).fit_predict(features)
        elif method == "MeanShift":
            from sklearn.cluster import MeanShift
            ms = MeanShift().fit(features)
            labels = ms.labels_
        elif method == "Spectral":
            from sklearn.cluster import SpectralClustering
            labels = SpectralClustering(n_clusters=k, random_state=42, affinity="nearest_neighbors").fit_predict(features)
        elif method == "AffinityPropagation":
            from sklearn.cluster import AffinityPropagation
            ap = AffinityPropagation(random_state=42).fit(features)
            labels = ap.labels_
        elif method == "OPTICS":
            from sklearn.cluster import OPTICS
            labels = OPTICS(min_samples=max(2, n_series // 10)).fit_predict(features)
            # OPTICS returns -1 for noise; remap to cluster 0
            labels = np.where(labels < 0, 0, labels)
        elif method == "HDBSCAN":
            try:
                from sklearn.cluster import HDBSCAN as HDBSCAN_cls
                labels = HDBSCAN_cls(min_cluster_size=max(2, n_series // 10)).fit_predict(features)
                labels = np.where(labels < 0, 0, labels)
            except ImportError:
                logger.warning("HDBSCAN not available; falling back to KMeans")
                labels = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(features)
        else:
            logger.warning(
                "Unknown clustering method '%s'; falling back to KMeans", method
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
            last_date = pd.to_datetime(ordered["demand_date"].max()).date()

            # Classify demand pattern and select algorithm
            pattern = self._classify_demand(values)
            point_fcst, residual_std = self._forecast_by_pattern(values, horizon, pattern)

            for step in range(1, horizon + 1):
                if bucket.startswith("D"):
                    f_date = last_date + timedelta(days=step)
                elif bucket.startswith("M"):
                    f_date = (pd.Timestamp(last_date) + pd.DateOffset(months=step)).date()
                else:
                    f_date = last_date + timedelta(weeks=step)

                p50 = max(0.0, point_fcst[step - 1])
                spread = residual_std * np.sqrt(step)  # widen with horizon
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
                        median=round(p50, 4),
                        p90=round(p90, 4),
                    )
                )
        return forecasts

    def _forecast_by_pattern(
        self, values: np.ndarray, horizon: int, pattern: str
    ) -> Tuple[np.ndarray, float]:
        """Select and run the best forecast algorithm for the demand pattern.

        Returns (point_forecasts[horizon], residual_std).
        """
        if pattern == "intermittent":
            return self._croston_forecast(values, horizon)
        elif pattern == "lumpy":
            return self._croston_forecast(values, horizon)

        # smooth or erratic: try Holt-Winters, then Holt, then SES
        try:
            return self._holtwinters_forecast(values, horizon)
        except Exception:
            pass
        try:
            return self._holt_forecast(values, horizon)
        except Exception:
            pass
        return self._ses_forecast(values, horizon)

    # ------------------------------------------------------------------
    # Exponential Smoothing Algorithms
    # ------------------------------------------------------------------

    @staticmethod
    def _ses_forecast(values: np.ndarray, horizon: int, alpha: float = 0.3) -> Tuple[np.ndarray, float]:
        """Simple Exponential Smoothing (level only, no trend/season)."""
        level = float(values[0])
        residuals = []
        for v in values[1:]:
            level = alpha * v + (1 - alpha) * level
            residuals.append(v - level)
        point = np.full(horizon, level)
        std = float(np.std(residuals)) if residuals else float(np.std(values)) or 1.0
        return point, std

    @staticmethod
    def _holt_forecast(values: np.ndarray, horizon: int, alpha: float = 0.3, beta: float = 0.1) -> Tuple[np.ndarray, float]:
        """Holt's Double Exponential Smoothing (level + trend)."""
        if len(values) < 3:
            return ForecastPipelineService._ses_forecast(values, horizon)
        level = float(values[0])
        trend = float(values[1] - values[0])
        residuals = []
        for v in values[1:]:
            prev_level = level
            level = alpha * v + (1 - alpha) * (level + trend)
            trend = beta * (level - prev_level) + (1 - beta) * trend
            residuals.append(v - (prev_level + trend))
        point = np.array([level + trend * (i + 1) for i in range(horizon)])
        point = np.maximum(point, 0.0)
        std = float(np.std(residuals)) if residuals else 1.0
        return point, std

    @staticmethod
    def _holtwinters_forecast(values: np.ndarray, horizon: int) -> Tuple[np.ndarray, float]:
        """Holt-Winters Triple Exponential Smoothing via statsmodels.

        Automatically selects additive or multiplicative seasonality.
        Falls back to Holt if seasonal period not detected or data too short.
        """
        from statsmodels.tsa.holtwinters import ExponentialSmoothing

        n = len(values)
        # Need at least 2 full seasonal cycles; try common periods
        seasonal_period = None
        for sp in [12, 4, 52, 7]:
            if n >= 2 * sp:
                seasonal_period = sp
                break
        if seasonal_period is None:
            return ForecastPipelineService._holt_forecast(values, horizon)

        # Try additive first, fall back to multiplicative if all values > 0
        series = pd.Series(values.astype(float))
        try:
            model = ExponentialSmoothing(
                series, trend="add", seasonal="add", seasonal_periods=seasonal_period
            ).fit(optimized=True)
        except Exception:
            if (values > 0).all():
                model = ExponentialSmoothing(
                    series, trend="add", seasonal="mul", seasonal_periods=seasonal_period
                ).fit(optimized=True)
            else:
                raise

        forecast = model.forecast(horizon).to_numpy()
        forecast = np.maximum(forecast, 0.0)
        residuals = (model.fittedvalues - series).to_numpy()
        std = float(np.std(residuals)) if len(residuals) > 0 else 1.0
        return forecast, std

    @staticmethod
    def _croston_forecast(values: np.ndarray, horizon: int, alpha: float = 0.15) -> Tuple[np.ndarray, float]:
        """Croston's method for intermittent demand.

        Separately smooths demand size and inter-arrival interval.
        """
        if len(values) < 2 or np.count_nonzero(values) < 2:
            mean_val = float(np.mean(values)) if len(values) > 0 else 0.0
            return np.full(horizon, mean_val), float(np.std(values)) or 1.0

        # Initialize with first nonzero demand
        nz_indices = np.nonzero(values)[0]
        z = float(values[nz_indices[0]])  # demand size estimate
        p = float(nz_indices[1] - nz_indices[0]) if len(nz_indices) > 1 else 1.0  # inter-arrival interval

        q = 0  # periods since last demand
        residuals = []
        for v in values:
            q += 1
            if v > 0:
                z = alpha * v + (1 - alpha) * z
                p = alpha * q + (1 - alpha) * p
                residuals.append(v - (z / p if p > 0 else z))
                q = 0

        rate = z / p if p > 0 else z
        point = np.full(horizon, max(0.0, rate))
        std = float(np.std(residuals)) if residuals else float(np.std(values)) or 1.0
        return point, std

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

    @staticmethod
    def _compute_fitted_intervals(
        residuals: np.ndarray, p50: float, step: int
    ) -> Tuple[float, float]:
        """Compute P10/P90 from fitted residual distribution.

        Instead of assuming residuals are Normal (hardcoded z=1.28), fits the
        actual residual distribution and uses its quantiles. Falls back to
        Normal when there aren't enough residuals to fit reliably.

        Insight: Kravanja (2026) — forecast residuals for lumpy or erratic
        demand are often right-skewed (Lognormal) rather than symmetric
        (Normal), making 1.28*sigma intervals systematically miscalibrated.

        Args:
            residuals: Forecast residuals from the training portion
            p50: Point forecast (median) for this step
            step: Forecast horizon step (1, 2, ...) for widening

        Returns:
            (p10, p90) interval bounds
        """
        if len(residuals) < 15:
            # Not enough data to fit; use Normal assumption
            spread = float(np.std(residuals)) * np.sqrt(step) if len(residuals) > 0 else 1.0
            return max(0.0, p50 - 1.28 * spread), max(0.0, p50 + 1.28 * spread)

        try:
            from app.services.stochastic.distribution_fitter import DistributionFitter
            fitter = DistributionFitter()
            report = fitter.fit(residuals, candidates=["normal", "lognormal", "gamma"])

            # Sample from fitted distribution and scale by sqrt(step)
            samples = report.best.distribution.sample(size=5000, seed=42)
            scaled = samples * np.sqrt(step)
            p10_offset = float(np.percentile(scaled, 10))
            p90_offset = float(np.percentile(scaled, 90))

            return max(0.0, p50 + p10_offset), max(0.0, p50 + p90_offset)
        except Exception:
            # Fitting failed; fall back to Normal
            spread = float(np.std(residuals)) * np.sqrt(step)
            return max(0.0, p50 - 1.28 * spread), max(0.0, p50 + 1.28 * spread)
