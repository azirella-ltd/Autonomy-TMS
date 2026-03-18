"""
LightGBM-based demand forecaster.
Trains cluster-specific models, stores checkpoints to backend/checkpoints/lgbm/,
generates P10/P50/P90 via quantile regression.
No fallbacks — raises errors for missing data.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Quantile names and corresponding alpha values
_QUANTILES: Dict[str, float] = {
    "p10": 0.1,
    "p50": 0.5,
    "p90": 0.9,
}


def _wape(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Weighted Absolute Percentage Error (WAPE).

    WAPE = sum(|actual - predicted|) / sum(|actual|)
    """
    denom = float(np.sum(np.abs(actual)))
    if denom == 0.0:
        return 0.0
    return float(np.sum(np.abs(actual - predicted))) / denom


class LGBMForecaster:
    """Trains and serves LightGBM quantile models per (config_id, cluster_id).

    Three separate LightGBM models are trained per cluster:
      - P10 (alpha=0.1): lower bound
      - P50 (alpha=0.5): median / point forecast
      - P90 (alpha=0.9): upper bound

    Checkpoints are stored to:
      backend/checkpoints/lgbm/config_{config_id}_cluster_{cluster_id}_p{quantile}.txt
    """

    def __init__(
        self,
        config_id: int,
        n_estimators: int = 500,
        learning_rate: float = 0.05,
    ) -> None:
        self.config_id = config_id
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.checkpoint_dir = Path("backend/checkpoints/lgbm")
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(
        self,
        features: pd.DataFrame,
        targets: pd.Series,
        censored_mask: pd.Series,
        cluster_id: str,
        feature_cols: List[str],
    ) -> Dict[str, Any]:
        """Train P10, P50, P90 quantile models for a cluster.

        Args:
            features: Feature DataFrame from DemandFeatureEngineer.build_features().
            targets: Demand quantity Series aligned to features index.
            censored_mask: Boolean Series; True = censored row to exclude.
            cluster_id: Cluster identifier (used for checkpoint naming).
            feature_cols: Column names from features to use as model inputs.

        Returns:
            Dict with keys: wape_p50, mae_p50, n_samples (int), n_censored (int).

        Raises:
            ValueError: If fewer than 10 uncensored training samples are available.
            ImportError: If lightgbm is not installed.
        """
        import lightgbm as lgb  # Imported here so module loads without lgb installed

        # Exclude censored rows from training
        if len(censored_mask) > 0:
            aligned_mask = censored_mask.reindex(features.index, fill_value=False)
        else:
            aligned_mask = pd.Series(False, index=features.index)

        n_censored = int(aligned_mask.sum())
        X_train = features.loc[~aligned_mask, feature_cols].copy()
        y_train = targets.loc[~aligned_mask].copy()

        # Drop rows where any feature is NaN
        valid = X_train.notna().all(axis=1) & y_train.notna()
        X_train = X_train.loc[valid]
        y_train = y_train.loc[valid]

        n_samples = len(X_train)
        if n_samples < 10:
            raise ValueError(
                f"Insufficient uncensored training samples for cluster '{cluster_id}': "
                f"{n_samples} samples (need >= 10). "
                f"Total rows: {len(features)}, censored: {n_censored}."
            )

        # Cast bool columns to int so LightGBM handles them correctly
        for col in feature_cols:
            if col in X_train.columns and X_train[col].dtype == bool:
                X_train[col] = X_train[col].astype(int)

        y_np = y_train.to_numpy().astype(float)
        X_np = X_train.to_numpy().astype(float)

        base_params = {
            "objective": "quantile",
            "metric": "quantile",
            "n_estimators": self.n_estimators,
            "learning_rate": self.learning_rate,
            "num_leaves": 31,
            "min_child_samples": min(20, max(5, n_samples // 10)),
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "verbose": -1,
        }

        p50_preds: Optional[np.ndarray] = None

        for quantile_name, alpha in _QUANTILES.items():
            params = dict(base_params)
            params["alpha"] = alpha

            model = lgb.LGBMRegressor(**params)
            model.fit(X_np, y_np)

            checkpoint_path = self._checkpoint_path(cluster_id, quantile_name)
            model.booster_.save_model(str(checkpoint_path))
            logger.info(
                "Saved LightGBM checkpoint: %s (n=%d)", checkpoint_path.name, n_samples
            )

            if quantile_name == "p50":
                p50_preds = model.predict(X_np)

        # Compute metrics on P50 predictions
        wape_p50 = _wape(y_np, p50_preds) if p50_preds is not None else 0.0
        mae_p50 = float(np.mean(np.abs(y_np - p50_preds))) if p50_preds is not None else 0.0

        return {
            "wape_p50": round(wape_p50, 6),
            "mae_p50": round(mae_p50, 6),
            "n_samples": n_samples,
            "n_censored": n_censored,
        }

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(
        self,
        features: pd.DataFrame,
        cluster_id: str,
        feature_cols: List[str],
        n_periods: int = 13,
        last_date: Optional[date] = None,
        time_bucket: str = "W",
    ) -> pd.DataFrame:
        """Generate P10/P50/P90 predictions for n_periods ahead.

        Uses the most recent row of each (product_id, site_id) series in
        features as the feature vector for prediction. The same feature
        vector is used for all n_periods (direct/flat forecast strategy).

        Args:
            features: Feature DataFrame from DemandFeatureEngineer.
            cluster_id: Cluster identifier matching a saved checkpoint.
            feature_cols: Column names to use as model inputs.
            n_periods: Number of periods ahead to generate.
            last_date: Most recent date in the historical series.
                       If None, inferred from features['date'].
            time_bucket: 'D', 'W', or 'M' to determine forecast step size.

        Returns:
            DataFrame with columns:
                [date, product_id, site_id, p10, p50, p90]

        Raises:
            FileNotFoundError: If checkpoint files are missing.
        """
        import lightgbm as lgb

        model_p10 = self._load_model(cluster_id, "p10")
        model_p50 = self._load_model(cluster_id, "p50")
        model_p90 = self._load_model(cluster_id, "p90")

        # Use last row of each (product_id, site_id) as the prediction feature vector
        if "date" not in features.columns:
            raise ValueError("features must contain a 'date' column")

        latest = (
            features.sort_values("date")
            .groupby(["product_id", "site_id"])
            .last()
            .reset_index()
        )

        # Prepare feature matrix
        available_cols = [c for c in feature_cols if c in latest.columns]
        if not available_cols:
            raise ValueError(
                f"None of the feature_cols found in features DataFrame. "
                f"Expected: {feature_cols[:5]}..., Got: {list(latest.columns[:10])}..."
            )

        X = latest[available_cols].copy()
        for col in available_cols:
            if X[col].dtype == bool:
                X[col] = X[col].astype(int)
        X_np = X.fillna(0).to_numpy().astype(float)

        raw_p10 = model_p10.predict(X_np)
        raw_p50 = model_p50.predict(X_np)
        raw_p90 = model_p90.predict(X_np)

        # Enforce monotonicity: P10 <= P50 <= P90
        p10_arr = np.minimum(raw_p10, raw_p50)
        p90_arr = np.maximum(raw_p50, raw_p90)
        p50_arr = np.clip(raw_p50, p10_arr, p90_arr)

        # Clip negatives
        p10_arr = np.maximum(p10_arr, 0.0)
        p50_arr = np.maximum(p50_arr, 0.0)
        p90_arr = np.maximum(p90_arr, 0.0)

        # Build output rows: repeat each series for each forecast step
        bucket = time_bucket.upper()
        rows = []
        for idx, row in latest.iterrows():
            if last_date is not None:
                base = last_date
            elif pd.notna(row.get("date")):
                base = pd.to_datetime(row["date"]).date()
            else:
                continue

            p10_val = float(p10_arr[idx if isinstance(idx, int) else latest.index.get_loc(idx)])
            p50_val = float(p50_arr[idx if isinstance(idx, int) else latest.index.get_loc(idx)])
            p90_val = float(p90_arr[idx if isinstance(idx, int) else latest.index.get_loc(idx)])

            for step in range(1, n_periods + 1):
                if bucket.startswith("D"):
                    f_date = base + timedelta(days=step)
                elif bucket.startswith("M"):
                    f_date = (pd.Timestamp(base) + pd.DateOffset(months=step)).date()
                else:
                    f_date = base + timedelta(weeks=step)

                rows.append({
                    "date": f_date,
                    "product_id": str(row["product_id"]),
                    "site_id": row["site_id"],
                    "p10": round(p10_val, 4),
                    "p50": round(p50_val, 4),
                    "p90": round(p90_val, 4),
                })

        return pd.DataFrame(rows, columns=["date", "product_id", "site_id", "p10", "p50", "p90"])

    # ------------------------------------------------------------------
    # Checkpoint helpers
    # ------------------------------------------------------------------

    def _checkpoint_path(self, cluster_id: str, quantile: str) -> Path:
        return self.checkpoint_dir / f"config_{self.config_id}_cluster_{cluster_id}_p{quantile}.txt"

    def _load_model(self, cluster_id: str, quantile: str):
        """Load a saved LightGBM Booster from checkpoint.

        Raises:
            FileNotFoundError: If the checkpoint file does not exist.
        """
        import lightgbm as lgb

        path = self._checkpoint_path(cluster_id, quantile)
        if not path.exists():
            raise FileNotFoundError(
                f"No LightGBM checkpoint for config={self.config_id} "
                f"cluster={cluster_id} p{quantile}. "
                f"Expected at: {path}"
            )
        return lgb.Booster(model_file=str(path))

    def checkpoint_exists(self, cluster_id: str) -> bool:
        """Return True if all three quantile checkpoints exist for this cluster."""
        return all(
            self._checkpoint_path(cluster_id, q).exists()
            for q in _QUANTILES
        )
