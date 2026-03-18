"""
LightGBM integration pipeline for demand forecasting.
Replaces Holt-Winters Stage 4 in ForecastPipelineService when LightGBM
checkpoints exist or when training is triggered.
Falls back to Holt-Winters for series with insufficient history (< 26 observations).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from app.services.demand_forecasting.event_tagger import EventTagger
from app.services.demand_forecasting.feature_engineer import DemandFeatureEngineer
from app.services.demand_forecasting.lgbm_forecaster import LGBMForecaster

logger = logging.getLogger(__name__)

# Minimum number of historical observations required to use LightGBM.
# Series below this threshold fall back to Holt-Winters.
_MIN_LGBM_OBSERVATIONS = 26


class LGBMForecastPipeline:
    """Integrates LightGBM into the ForecastPipelineService as Stage 4.

    Designed to be called after Stage 3 (feature selection) inside
    ForecastPipelineService.run_pipeline(). Results are returned in the
    same SeriesForecast-compatible format that Stage 4 currently produces,
    so they can be merged with or override the Holt-Winters results.

    Usage example (inside ForecastPipelineService.run_pipeline):
        lgbm_pipeline = LGBMForecastPipeline(config_id=run.config_id)
        lgbm_results = lgbm_pipeline.run_stage4_lgbm(
            run_id=run_id,
            config_id=run.config_id,
            history=history,
            cluster_results=clusters,
            censored_flags=censored_flags,
            n_periods=cfg.forecast_horizon or 13,
            time_bucket=cfg.time_bucket or "W",
            retrain=run_full,
        )
        # Merge: lgbm_results override holt_winters_results for qualifying series
        for uid, lgbm_sf_list in lgbm_results["predictions"].items():
            holt_winters_results[uid] = lgbm_sf_list  # LightGBM wins
    """

    def __init__(self, config_id: int) -> None:
        self.config_id = config_id
        self.event_tagger = EventTagger()
        self.feature_engineer = DemandFeatureEngineer()
        self.forecaster = LGBMForecaster(config_id=config_id)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run_stage4_lgbm(
        self,
        run_id: int,
        config_id: int,
        history: pd.DataFrame,
        cluster_results: Dict[str, int],
        censored_flags: Dict,
        n_periods: int = 13,
        time_bucket: str = "W",
        retrain: bool = False,
    ) -> Dict[str, Any]:
        """Execute LightGBM Stage 4 for all qualifying series.

        Args:
            run_id: ForecastPipelineRun.id (for logging only).
            config_id: Supply chain config ID.
            history: Raw history DataFrame with columns
                     [unique_id, product_id, site_id, demand_date, actual].
                     Must be the same object produced by ForecastPipelineService._load_history().
            cluster_results: Dict mapping unique_id → cluster_id int,
                             from ForecastPipelineService._cluster_series().
            censored_flags: Dict from DemandProcessor or {} if not available.
            n_periods: Number of forecast periods to generate.
            time_bucket: 'D', 'W', or 'M'.
            retrain: If True, always retrain even if checkpoints exist.

        Returns:
            Dict with keys:
                "predictions": Dict[unique_id, List[SeriesForecast-compatible dicts]]
                    Each item: {product_id, site_id, cluster_id, forecast_date,
                                p10, p50, median, p90}
                "lgbm_series_count": int — series using LightGBM
                "lgbm_fallback_count": int — series falling back to Holt-Winters
                "lgbm_wape_p50": float — average WAPE P50 across trained clusters
                "lgbm_checkpoint_path": str — checkpoint directory path
                "cluster_metrics": Dict[cluster_id, metrics_dict]
        """
        if history.empty:
            return self._empty_result()

        # Build a demand_df suitable for feature engineering
        # (rename demand_date → date, actual → quantity)
        demand_df = history.rename(columns={"demand_date": "date", "actual": "quantity"}).copy()
        demand_df["date"] = pd.to_datetime(demand_df["date"])

        # Build calendar features across all dates in history
        all_dates = pd.DatetimeIndex(demand_df["date"].unique())
        cal_df = self.event_tagger.tag_calendar(all_dates)

        # Determine which series have sufficient history
        series_counts = (
            history.groupby("unique_id")["actual"].count()
        )
        sufficient_uids = set(
            series_counts[series_counts >= _MIN_LGBM_OBSERVATIONS].index
        )
        insufficient_uids = set(cluster_results.keys()) - sufficient_uids

        lgbm_fallback_count = len(insufficient_uids)
        lgbm_series_count = len(sufficient_uids)

        logger.info(
            "Run %d LightGBM Stage 4: %d series qualify (>= %d obs), %d fall back",
            run_id,
            lgbm_series_count,
            _MIN_LGBM_OBSERVATIONS,
            lgbm_fallback_count,
        )

        if lgbm_series_count == 0:
            result = self._empty_result()
            result["lgbm_fallback_count"] = lgbm_fallback_count
            return result

        # Group qualifying series by cluster
        cluster_to_uids: Dict[int, List[str]] = {}
        for uid in sufficient_uids:
            cluster_id = cluster_results.get(uid, 0)
            cluster_to_uids.setdefault(cluster_id, []).append(uid)

        all_predictions: Dict[str, List[dict]] = {}
        cluster_metrics: Dict[str, dict] = {}
        wape_values: List[float] = []

        for cluster_id, uids in cluster_to_uids.items():
            cluster_str = str(cluster_id)

            # Build feature dataset for this cluster's series
            cluster_mask = demand_df["unique_id"].isin(uids)
            cluster_demand = demand_df.loc[cluster_mask].copy()

            if cluster_demand.empty:
                continue

            # Build censored mask aligned to cluster_demand index
            cluster_censored = self._build_censored_mask(
                cluster_demand, censored_flags
            )

            try:
                features_df = self.feature_engineer.build_features(
                    demand_df=cluster_demand[["date", "product_id", "site_id", "quantity"]],
                    event_df=cal_df,
                    censored_mask=cluster_censored,
                )
            except Exception as exc:
                logger.warning(
                    "Feature engineering failed for cluster %s: %s — skipping",
                    cluster_str,
                    exc,
                )
                # Fall back to Holt-Winters for this cluster
                lgbm_fallback_count += len(uids)
                lgbm_series_count -= len(uids)
                continue

            feature_cols = [
                c for c in self.feature_engineer.get_feature_columns()
                if c in features_df.columns
            ]

            if not feature_cols:
                logger.warning("No feature columns available for cluster %s", cluster_str)
                lgbm_fallback_count += len(uids)
                lgbm_series_count -= len(uids)
                continue

            targets = features_df["quantity"]

            # Train or load models for this cluster
            should_train = retrain or not self.forecaster.checkpoint_exists(cluster_str)

            if should_train:
                try:
                    metrics = self.forecaster.train(
                        features=features_df,
                        targets=targets,
                        censored_mask=cluster_censored.reindex(features_df.index, fill_value=False),
                        cluster_id=cluster_str,
                        feature_cols=feature_cols,
                    )
                    cluster_metrics[cluster_str] = metrics
                    wape_values.append(metrics["wape_p50"])
                    logger.info(
                        "Trained LightGBM cluster %s: WAPE_P50=%.4f n=%d",
                        cluster_str,
                        metrics["wape_p50"],
                        metrics["n_samples"],
                    )
                except Exception as exc:
                    logger.warning(
                        "LightGBM training failed for cluster %s: %s — falling back",
                        cluster_str,
                        exc,
                    )
                    lgbm_fallback_count += len(uids)
                    lgbm_series_count -= len(uids)
                    continue

            # Generate predictions for each series in this cluster
            pred_features = self.feature_engineer.build_prediction_features(
                demand_df=cluster_demand[["date", "product_id", "site_id", "quantity"]],
                event_df=cal_df,
            )

            for uid in uids:
                uid_parts = uid.split("|", 1)
                if len(uid_parts) != 2:
                    logger.warning("Unexpected unique_id format: %s", uid)
                    continue

                product_id, site_id = uid_parts[0], uid_parts[1]

                uid_features = pred_features[
                    (pred_features["product_id"] == product_id) &
                    (pred_features["site_id"].astype(str) == site_id)
                ].copy()

                if uid_features.empty:
                    logger.warning("No prediction features for uid=%s", uid)
                    lgbm_fallback_count += 1
                    lgbm_series_count -= 1
                    continue

                # Get last date for this series
                uid_history = history[history["unique_id"] == uid]
                if uid_history.empty:
                    continue
                last_date = pd.to_datetime(uid_history["demand_date"].max()).date()

                try:
                    pred_df = self.forecaster.predict(
                        features=uid_features,
                        cluster_id=cluster_str,
                        feature_cols=feature_cols,
                        n_periods=n_periods,
                        last_date=last_date,
                        time_bucket=time_bucket,
                    )
                except Exception as exc:
                    logger.warning(
                        "LightGBM prediction failed for uid=%s: %s — falling back",
                        uid,
                        exc,
                    )
                    lgbm_fallback_count += 1
                    lgbm_series_count -= 1
                    continue

                # Convert to SeriesForecast-compatible dicts
                uid_forecasts = []
                for _, row in pred_df.iterrows():
                    uid_forecasts.append({
                        "product_id": str(product_id),
                        "site_id": str(site_id),
                        "cluster_id": cluster_id,
                        "forecast_date": row["date"],
                        "p10": float(row["p10"]),
                        "p50": float(row["p50"]),
                        "median": float(row["p50"]),
                        "p90": float(row["p90"]),
                    })

                all_predictions[uid] = uid_forecasts

        avg_wape = float(np.mean(wape_values)) if wape_values else 0.0

        return {
            "predictions": all_predictions,
            "lgbm_series_count": lgbm_series_count,
            "lgbm_fallback_count": lgbm_fallback_count,
            "lgbm_wape_p50": round(avg_wape, 6),
            "lgbm_checkpoint_path": str(self.forecaster.checkpoint_dir),
            "cluster_metrics": cluster_metrics,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_censored_mask(
        self,
        cluster_demand: pd.DataFrame,
        censored_flags: Dict,
    ) -> pd.Series:
        """Build a boolean censored mask aligned to cluster_demand.index.

        censored_flags may use unique_id or (product_id, site_id, date) tuples
        as keys depending on DemandProcessor implementation.
        """
        mask = pd.Series(False, index=cluster_demand.index)

        if not censored_flags:
            return mask

        for idx, row in cluster_demand.iterrows():
            uid = row.get("unique_id", "")
            demand_date = row.get("date")

            # Try various key formats that DemandProcessor might use
            if uid in censored_flags:
                val = censored_flags[uid]
                if isinstance(val, bool):
                    mask.loc[idx] = val
                elif isinstance(val, dict) and demand_date is not None:
                    date_key = pd.to_datetime(demand_date).date() if demand_date else None
                    if date_key and date_key in val:
                        mask.loc[idx] = bool(val[date_key])
            elif demand_date is not None:
                date_key = pd.to_datetime(demand_date).date()
                if date_key in censored_flags:
                    mask.loc[idx] = bool(censored_flags[date_key])

        return mask

    @staticmethod
    def _empty_result() -> Dict[str, Any]:
        return {
            "predictions": {},
            "lgbm_series_count": 0,
            "lgbm_fallback_count": 0,
            "lgbm_wape_p50": 0.0,
            "lgbm_checkpoint_path": "",
            "cluster_metrics": {},
        }
