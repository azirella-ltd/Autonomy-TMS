"""
Feature engineering for LightGBM demand forecasting.
Ports lag/rolling/calendar feature logic from scripts/training/forecast_pipeline/lightgbm_prediction.py
into a FastAPI-compatible service class.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Default lag periods: weekly lags up to 1 year
_DEFAULT_LAG_PERIODS: List[int] = [1, 2, 3, 4, 8, 13, 26, 52]

# Default rolling windows: 4-week to 6-month windows
_DEFAULT_ROLLING_WINDOWS: List[int] = [4, 8, 13, 26]


class DemandFeatureEngineer:
    """Builds lag, rolling, and calendar features for LightGBM demand forecasting.

    All features are computed per (product_id, site_id) time series group.
    Censored periods are masked (set to NaN) before lag computation so stockout
    periods do not propagate misleading signal into lag features.
    """

    def __init__(
        self,
        lag_periods: Optional[List[int]] = None,
        rolling_windows: Optional[List[int]] = None,
    ) -> None:
        self.lag_periods: List[int] = lag_periods if lag_periods is not None else list(_DEFAULT_LAG_PERIODS)
        self.rolling_windows: List[int] = rolling_windows if rolling_windows is not None else list(_DEFAULT_ROLLING_WINDOWS)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_features(
        self,
        demand_df: pd.DataFrame,
        event_df: pd.DataFrame,
        censored_mask: pd.Series,
    ) -> pd.DataFrame:
        """Build features for model training.

        Args:
            demand_df: Columns [date, product_id, site_id, quantity].
                       'date' must be parseable by pd.to_datetime.
            event_df: Calendar/event features indexed by date.
                      Produced by EventTagger.tag_calendar().
                      Must contain columns: day_of_week, month, quarter,
                      week_of_year, is_weekend, is_month_end, is_quarter_end.
            censored_mask: Boolean Series indexed like demand_df index.
                           True = censored stockout period.
                           Censored rows have lag values set to NaN to prevent
                           them from propagating misleading signal.

        Returns:
            Wide feature DataFrame. Rows with NaN lag values (insufficient
            history) are dropped. Index is reset.

        Raises:
            ValueError: If demand_df is missing required columns.
        """
        self._validate_demand_df(demand_df)

        df = demand_df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values(["product_id", "site_id", "date"]).reset_index(drop=True)

        # Mask censored rows: set quantity to NaN so lags skip them
        if len(censored_mask) > 0:
            aligned_mask = censored_mask.reindex(df.index, fill_value=False)
            df.loc[aligned_mask, "quantity"] = np.nan

        df = self._add_lag_features(df, masked=True)
        df = self._add_rolling_features(df)
        df = self._add_calendar_features(df, event_df)

        # Drop rows with NaN in any lag feature (insufficient history)
        lag_cols = [f"lag_{n}" for n in self.lag_periods]
        existing_lag_cols = [c for c in lag_cols if c in df.columns]
        if existing_lag_cols:
            df = df.dropna(subset=existing_lag_cols)

        return df.reset_index(drop=True)

    def build_prediction_features(
        self,
        demand_df: pd.DataFrame,
        event_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """Build features for inference (no censored mask).

        Uses all available history to construct lag and rolling features
        for the most recent observations (which will serve as features for
        the prediction horizon).

        Args:
            demand_df: Columns [date, product_id, site_id, quantity].
            event_df: Calendar features indexed by date.

        Returns:
            Feature DataFrame for the latest row of each (product_id, site_id).

        Raises:
            ValueError: If demand_df is missing required columns.
        """
        self._validate_demand_df(demand_df)

        df = demand_df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values(["product_id", "site_id", "date"]).reset_index(drop=True)

        df = self._add_lag_features(df, masked=False)
        df = self._add_rolling_features(df)
        df = self._add_calendar_features(df, event_df)

        return df.reset_index(drop=True)

    def get_feature_columns(self) -> List[str]:
        """Return the ordered list of feature column names produced by this engineer."""
        lag_cols = [f"lag_{n}" for n in self.lag_periods]
        roll_cols = []
        for w in self.rolling_windows:
            roll_cols += [f"roll_{w}_mean", f"roll_{w}_std", f"roll_{w}_min", f"roll_{w}_max"]
        calendar_cols = [
            "day_of_week", "month", "quarter", "week_of_year",
            "is_weekend", "is_month_end", "is_quarter_end",
        ]
        return lag_cols + roll_cols + calendar_cols

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_demand_df(demand_df: pd.DataFrame) -> None:
        required = {"date", "product_id", "site_id", "quantity"}
        missing = required - set(demand_df.columns)
        if missing:
            raise ValueError(
                f"demand_df is missing required columns: {missing}. "
                f"Columns present: {list(demand_df.columns)}"
            )

    def _add_lag_features(self, df: pd.DataFrame, masked: bool) -> pd.DataFrame:
        """Add lag_N columns per (product_id, site_id) group."""
        for n in self.lag_periods:
            df[f"lag_{n}"] = (
                df.groupby(["product_id", "site_id"])["quantity"]
                .shift(n)
            )
        return df

    def _add_rolling_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add rolling mean/std/min/max columns per (product_id, site_id) group."""
        for w in self.rolling_windows:
            grouped = df.groupby(["product_id", "site_id"])["quantity"]
            # min_periods=1 so partial windows don't produce NaN
            df[f"roll_{w}_mean"] = grouped.transform(
                lambda s: s.rolling(w, min_periods=1).mean()
            )
            df[f"roll_{w}_std"] = grouped.transform(
                lambda s: s.rolling(w, min_periods=1).std().fillna(0.0)
            )
            df[f"roll_{w}_min"] = grouped.transform(
                lambda s: s.rolling(w, min_periods=1).min()
            )
            df[f"roll_{w}_max"] = grouped.transform(
                lambda s: s.rolling(w, min_periods=1).max()
            )
        return df

    def _add_calendar_features(
        self, df: pd.DataFrame, event_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Join calendar features from event_df onto df by date."""
        if event_df.empty:
            # Add zero-filled calendar columns so downstream code doesn't break
            for col in ["day_of_week", "month", "quarter", "week_of_year",
                        "is_weekend", "is_month_end", "is_quarter_end"]:
                df[col] = 0
            return df

        # event_df is indexed by DatetimeIndex; reset to column for merge
        cal = event_df.copy()
        if not isinstance(cal.index, pd.DatetimeIndex):
            raise ValueError("event_df must have a DatetimeIndex")

        cal = cal.reset_index().rename(columns={"index": "date"})
        cal["date"] = pd.to_datetime(cal["date"])

        # Only keep the columns we need
        cal_cols = [c for c in [
            "date", "day_of_week", "month", "quarter", "week_of_year",
            "is_weekend", "is_month_end", "is_quarter_end",
        ] if c in cal.columns]
        cal = cal[cal_cols]

        df = df.merge(cal, on="date", how="left")

        # Fill missing calendar values for dates not in event_df
        for col in ["day_of_week", "month", "quarter", "week_of_year"]:
            if col in df.columns:
                df[col] = df[col].fillna(0).astype(int)
        for col in ["is_weekend", "is_month_end", "is_quarter_end"]:
            if col in df.columns:
                df[col] = df[col].fillna(False).astype(bool)

        return df
