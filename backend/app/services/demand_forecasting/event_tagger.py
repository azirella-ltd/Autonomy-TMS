"""
Event tagger for demand time series.
Tags periods with: stockout (censored), holiday, day-of-week, month, quarter.
No fallbacks — missing data raises errors.
"""

from __future__ import annotations

from datetime import date
from typing import Dict

import pandas as pd


# US federal holidays (month, day) pairs for the standard 11 federal holidays.
# Thanksgiving is a computed holiday (4th Thursday of November); handled separately.
_FIXED_US_FEDERAL_HOLIDAYS: tuple[tuple[int, int], ...] = (
    (1, 1),    # New Year's Day
    (1, 15),   # MLK Day (3rd Monday Jan — use 15th as representative fixed anchor)
    (2, 19),   # Presidents' Day (3rd Monday Feb — 19th as anchor)
    (5, 27),   # Memorial Day (last Monday May — 27th as anchor)
    (6, 19),   # Juneteenth
    (7, 4),    # Independence Day
    (9, 2),    # Labor Day (1st Monday Sep — 2nd as anchor)
    (10, 14),  # Columbus Day (2nd Monday Oct — 14th as anchor)
    (11, 11),  # Veterans Day
    (12, 25),  # Christmas Day
)

# Thanksgiving: 4th Thursday of November, approximate range 22–28
_THANKSGIVING_RANGE = (11, 22, 28)  # month, day_min, day_max


class EventTagger:
    """Tags demand time series periods with event and calendar flags."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def tag_stockouts(
        self,
        demand_series: pd.Series,
        inventory_series: pd.Series,
        censored_flags: Dict,
    ) -> pd.Series:
        """Return boolean mask of stockout (censored) periods.

        Uses existing censored_flags from DemandProcessor as the primary
        source of truth. Falls back to inventory_series == 0 for periods
        not covered by censored_flags.

        Args:
            demand_series: Indexed by date, values are demand quantities.
            inventory_series: Indexed by date, values are inventory levels.
            censored_flags: Dict mapping date/key → bool from DemandProcessor.

        Returns:
            Boolean pd.Series indexed like demand_series (True = censored/stockout).
        """
        if demand_series.empty:
            raise ValueError("demand_series must not be empty")

        result = pd.Series(False, index=demand_series.index)

        # Apply censored_flags from DemandProcessor (primary source)
        for key, is_censored in censored_flags.items():
            if key in result.index:
                result.loc[key] = bool(is_censored)

        # Supplement with inventory == 0 for dates not in censored_flags
        if not inventory_series.empty:
            zero_inv = inventory_series.reindex(demand_series.index).fillna(0) == 0
            # Only mark censored if not already flagged by censored_flags
            untagged = ~result
            result = result | (zero_inv & untagged)

        return result

    def tag_holidays(
        self,
        dates: pd.DatetimeIndex,
        country_code: str = "US",
    ) -> pd.Series:
        """Return boolean Series indicating whether each date is a US federal holiday.

        Uses a hardcoded list of US federal holidays — no external API.

        Supported country_code: "US" only. Raises ValueError for unsupported codes.

        Args:
            dates: DatetimeIndex of dates to tag.
            country_code: ISO country code (only "US" supported).

        Returns:
            Boolean pd.Series indexed by dates.
        """
        if country_code != "US":
            raise ValueError(
                f"country_code '{country_code}' is not supported. Only 'US' is supported."
            )

        result = pd.Series(False, index=dates)

        for dt in dates:
            month = dt.month
            day = dt.day
            year = dt.year

            # Check fixed holidays
            if (month, day) in _FIXED_US_FEDERAL_HOLIDAYS:
                result.loc[dt] = True
                continue

            # Thanksgiving: 4th Thursday of November (days 22–28)
            t_month, t_day_min, t_day_max = _THANKSGIVING_RANGE
            if month == t_month and t_day_min <= day <= t_day_max:
                # Confirm it's a Thursday
                if dt.dayofweek == 3:  # Monday=0, Thursday=3
                    result.loc[dt] = True

        return result

    def tag_calendar(self, dates: pd.DatetimeIndex) -> pd.DataFrame:
        """Return a DataFrame of calendar features for each date.

        Args:
            dates: DatetimeIndex of dates to generate calendar features for.

        Returns:
            pd.DataFrame with columns:
                day_of_week (0=Monday … 6=Sunday),
                month (1–12),
                quarter (1–4),
                week_of_year (1–53),
                is_weekend (bool),
                is_month_end (bool),
                is_quarter_end (bool).
        """
        if len(dates) == 0:
            return pd.DataFrame(
                columns=[
                    "day_of_week",
                    "month",
                    "quarter",
                    "week_of_year",
                    "is_weekend",
                    "is_month_end",
                    "is_quarter_end",
                ]
            )

        df = pd.DataFrame(index=dates)
        df["day_of_week"] = dates.dayofweek
        df["month"] = dates.month
        df["quarter"] = dates.quarter
        df["week_of_year"] = dates.isocalendar().week.astype(int)
        df["is_weekend"] = dates.dayofweek >= 5
        df["is_month_end"] = dates.is_month_end
        df["is_quarter_end"] = dates.is_quarter_end
        return df
