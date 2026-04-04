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
        category_demand_df: Optional[pd.DataFrame] = None,
        external_signals_df: Optional[pd.DataFrame] = None,
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
            category_demand_df: Optional cross-product features.
                      Columns: [date, product_id, site_id, category_demand,
                      family_demand, sibling_count, category_share,
                      category_trend]. If None, cross-product features skipped.
            external_signals_df: Optional external signal features.
                      Columns: [date, site_id, signal_type, signal_value].
                      Pivoted to one column per signal_type. If None, skipped.

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
        df = self._add_cross_product_features(df, category_demand_df)
        df = self._add_external_signal_features(df, external_signals_df)

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

    # Cross-product feature columns (added when category_demand_df is provided)
    CROSS_PRODUCT_COLS = [
        "category_demand",       # Total category demand (all siblings)
        "family_demand",         # Total family demand (parent node)
        "category_share",        # This product's share of category demand
        "category_trend",        # Category period-over-period change
        "sibling_count",         # Number of siblings in category
    ]

    # External signal feature columns (added when external_signals_df is provided)
    EXTERNAL_SIGNAL_TYPES = [
        "weather_temp_anomaly",  # Temperature deviation from seasonal norm
        "weather_precip_anomaly",  # Precipitation anomaly
        "economic_gdp_growth",   # GDP growth rate
        "economic_consumer_conf",  # Consumer confidence index
        "commodity_price_index", # Raw material cost index
        "pos_sell_through_ratio",  # POS actual vs forecast ratio
    ]

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
        # Cross-product and external signal columns are optional
        # (only present when corresponding data is provided)
        return lag_cols + roll_cols + calendar_cols

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _add_cross_product_features(
        self, df: pd.DataFrame, category_demand_df: Optional[pd.DataFrame]
    ) -> pd.DataFrame:
        """Add cross-product features: category demand, share, trend.

        These features capture demand dependencies between products:
        - category_demand: Total demand across all products in the category.
          If category demand rises but this SKU is flat → losing share.
        - family_demand: Demand at the product family level.
        - category_share: This product's fraction of category demand.
          Share shifts indicate cannibalization or demand migration.
        - category_trend: Period-over-period change in category demand.
          Captures macro category growth/decline.
        - sibling_count: Number of products in the same category.
          More siblings = more cannibalization risk.
        """
        if category_demand_df is None or category_demand_df.empty:
            return df

        try:
            cat_df = category_demand_df.copy()
            cat_df["date"] = pd.to_datetime(cat_df["date"])

            # Merge on date + product_id + site_id
            merge_cols = ["date", "product_id", "site_id"]
            available_cols = [c for c in merge_cols if c in cat_df.columns]
            if len(available_cols) < 2:
                logger.debug("category_demand_df missing merge columns, skipping cross-product features")
                return df

            feature_cols = [c for c in self.CROSS_PRODUCT_COLS if c in cat_df.columns]
            if not feature_cols:
                return df

            df = df.merge(
                cat_df[available_cols + feature_cols],
                on=available_cols,
                how="left",
            )

            # Fill NaN with neutral values
            for col in feature_cols:
                if col in df.columns:
                    if col == "category_share":
                        df[col] = df[col].fillna(0.0)
                    elif col == "sibling_count":
                        df[col] = df[col].fillna(1).astype(int)
                    else:
                        df[col] = df[col].fillna(0.0)

            logger.debug(
                "Cross-product features added: %s (%d rows matched)",
                feature_cols, df[feature_cols[0]].notna().sum(),
            )
        except Exception as e:
            logger.warning("Failed to add cross-product features: %s", e)

        return df

    def _add_external_signal_features(
        self, df: pd.DataFrame, signals_df: Optional[pd.DataFrame]
    ) -> pd.DataFrame:
        """Add external signal features: weather, economic, POS, commodity.

        External signals are pivoted from long format (date, site_id, signal_type,
        signal_value) to wide format (one column per signal type).

        Supported signal types:
        - weather_temp_anomaly: Temperature deviation from seasonal norm
        - weather_precip_anomaly: Precipitation deviation
        - economic_gdp_growth: GDP growth rate (national)
        - economic_consumer_conf: Consumer confidence index
        - commodity_price_index: Raw material cost index
        - pos_sell_through_ratio: POS sell-through vs forecast
        """
        if signals_df is None or signals_df.empty:
            return df

        try:
            sig = signals_df.copy()
            sig["date"] = pd.to_datetime(sig["date"])

            # Pivot signal_type ��� columns
            if "signal_type" in sig.columns and "signal_value" in sig.columns:
                pivot_cols = ["date"]
                if "site_id" in sig.columns:
                    pivot_cols.append("site_id")

                pivoted = sig.pivot_table(
                    index=pivot_cols,
                    columns="signal_type",
                    values="signal_value",
                    aggfunc="mean",
                ).reset_index()

                # Flatten MultiIndex columns
                if hasattr(pivoted.columns, "droplevel"):
                    pivoted.columns = [
                        c[0] if isinstance(c, tuple) and c[1] == "" else
                        c[1] if isinstance(c, tuple) else c
                        for c in pivoted.columns
                    ]

                df = df.merge(pivoted, on=pivot_cols, how="left")

                # Fill missing signal values with 0 (neutral)
                for col in self.EXTERNAL_SIGNAL_TYPES:
                    if col in df.columns:
                        df[col] = df[col].fillna(0.0)

                added = [c for c in self.EXTERNAL_SIGNAL_TYPES if c in df.columns]
                if added:
                    logger.debug("External signal features added: %s", added)

        except Exception as e:
            logger.warning("Failed to add external signal features: %s", e)

        return df

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
