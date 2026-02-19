"""Utilities for handling time bucket calculations across the Beer Game."""
from __future__ import annotations

from datetime import date, timedelta
from enum import Enum
from typing import Optional

import calendar

__all__ = [
    "TimeBucket",
    "DEFAULT_START_DATE",
    "normalize_time_bucket",
    "compute_period_start",
    "compute_period_end",
]


class TimeBucket(str, Enum):
    """Supported aggregation levels for the simulation timeline."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"


DEFAULT_START_DATE = date(2025, 1, 6)  # First Monday of January 2025


def normalize_time_bucket(value: Optional[str | TimeBucket]) -> TimeBucket:
    """Return a canonical :class:`TimeBucket` from a raw value."""

    if isinstance(value, TimeBucket):
        return value
    if isinstance(value, str):
        token = value.strip().lower()
        for bucket in TimeBucket:
            if bucket.value == token:
                return bucket
    return TimeBucket.WEEK


def _add_months(value: date, months: int) -> date:
    """Return ``value`` shifted forward by ``months`` months."""

    if months == 0:
        return value

    month_index = (value.month - 1) + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(value.day, last_day)
    return date(year, month, day)


def compute_period_start(start_date: date, step_index: int, bucket: TimeBucket) -> date:
    """Return the start date for the ``step_index``-th period."""

    if step_index <= 0:
        return start_date

    if bucket == TimeBucket.DAY:
        return start_date + timedelta(days=step_index)
    if bucket == TimeBucket.WEEK:
        return start_date + timedelta(weeks=step_index)
    if bucket == TimeBucket.MONTH:
        return _add_months(start_date, step_index)
    return start_date


def compute_period_end(period_start: date, bucket: TimeBucket) -> date:
    """Compute the inclusive end date for a period starting at ``period_start``."""

    if bucket == TimeBucket.DAY:
        return period_start
    if bucket == TimeBucket.WEEK:
        return period_start + timedelta(days=6)
    if bucket == TimeBucket.MONTH:
        next_start = _add_months(period_start, 1)
        return next_start - timedelta(days=1)
    return period_start
